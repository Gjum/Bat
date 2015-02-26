import logging
import zlib

from twisted.internet import protocol, reactor

from quarry.util.crypto import Cipher
from quarry.util.buffer import Buffer, BufferUnderrun
from quarry.util.tasks import Tasks
from quarry.util.dispatch import PacketDispatcher, register


logging.basicConfig(format="%(name)s | %(levelname)s | %(message)s")

protocol_modes = {
    0: 'init',
    1: 'status',
    2: 'login',
    3: 'play'
}
protocol_modes_inv = dict(((v, k) for k, v in protocol_modes.iteritems()))


class ProtocolError(Exception):
    pass


class Protocol(protocol.Protocol, PacketDispatcher, object):
    """Shared logic between the client and server"""

    protocol_version = None
    protocol_mode = "init"
    compression_threshold = None
    compression_enabled = False

    in_game = False
    closed = False

    def __init__(self, factory, addr):
        self.factory = factory
        self.recv_addr = addr

        self.buff_type = self.factory.buff_type
        self.recv_buff = self.buff_type()
        self.cipher = Cipher()
        self.tasks = Tasks()

        self.logger = logging.getLogger("%s{%s}" % (
            self.__class__.__name__,
            self.recv_addr.host))
        self.logger.setLevel(self.factory.log_level)

        self.register_handlers()

        self.connection_timer = self.tasks.add_delay(
            self.factory.connection_timeout,
            self.connection_timed_out)

        self.setup()

    ### Fix ugly twisted methods ----------------------------------------------

    def dataReceived(self, data):
        return self.data_received(data)

    def connectionMade(self):
        return self.connection_made()

    def connectionLost(self, reason=None):
        return self.connection_lost(reason)

    ### Convenience functions -------------------------------------------------

    def check_protocol_mode_switch(self, mode):
        transitions = [
            ("init", "status"),
            ("init", "login"),
            ("login", "play")
        ]

        if (self.protocol_mode, mode) not in transitions:
            raise ProtocolError("Cannot switch protocol mode from %s to %s"
                                % (self.protocol_mode, mode))

    def switch_protocol_mode(self, mode):
        self.check_protocol_mode_switch(mode)
        self.protocol_mode = mode

    def set_compression(self, compression_threshold):
        if not self.compression_enabled:
            self.compression_enabled = True
            self.logger.debug("Compression enabled")

        self.compression_threshold = compression_threshold
        self.logger.debug("Compression threshold set to %d bytes" % compression_threshold)

    def close(self, reason=None):
        """Closes the connection"""

        if not self.closed:
            if reason:
                reason = "Closing connection: %s" % reason
            else:
                reason = "Closing connection"

            if self.in_game:
                self.logger.info(reason)
            else:
                self.logger.debug(reason)

            self.transport.loseConnection()
            self.closed = True

    def log_packet(self, prefix, ident):
        """Logs a packet at debug level"""

        self.logger.debug("Packet %s %s/%02x" % (
            prefix,
            self.protocol_mode,
            ident))

    ### General callbacks -----------------------------------------------------

    def setup(self):
        """Called when the object's initialiser is finished"""

        pass

    def protocol_error(self, err):
        """Called when a protocol error occurs"""

        msg = "Protocol error: %s" % err
        self.logger.error(msg)
        self.close(msg)

    ### Connection callbacks --------------------------------------------------

    def connection_made(self):
        """Called when the connection is established"""

        self.logger.debug("Connection made")

    def connection_lost(self, reason=None):
        """Called when the connection is lost"""

        self.closed = True
        if self.in_game:
            self.player_left()
        self.logger.debug("Connection lost")

        self.tasks.stop_all()

    def connection_timed_out(self):
        """Called when the connection has been idle too long"""

        self.close("Connection timed out")

    ### Auth callbacks --------------------------------------------------------

    def auth_ok(self, data):
        """Called when auth with mojang succeeded (online mode only)"""

        pass

    def auth_failed(self, err):
        """Called when auth with mojang failed (online mode only)"""

        self.close("Auth failed: %s" % err.value)

    ### Player callbacks ------------------------------------------------------

    def player_joined(self):
        """Called when the protocol mode has switched to "play" """

        self.in_game = True

    def player_left(self):
        """Called when the player leaves"""

        pass

    ### Packet handling -------------------------------------------------------

    def data_received(self, data):
        # Decrypt data
        data = self.cipher.decrypt(data)

        # Add it to our buffer
        self.recv_buff.add(data)

        # Read some packets
        while not self.closed:
            # Save the buffer, in case we read an incomplete packet
            self.recv_buff.save()

            # Try to read a packet
            try:
                packet_length = self.recv_buff.unpack_varint()
                packet_body = self.recv_buff.unpack_raw(packet_length)

            # Incomplete packet read, restore the buffer.
            except BufferUnderrun:
                self.recv_buff.restore()
                break

            # Load the packet body into a buffer
            packet_buff = self.buff_type()
            packet_buff.add(packet_body)

            try: # Catch protocol errors
                try: # Catch buffer overrun/underrun
                    if self.compression_enabled:
                        uncompressed_length = packet_buff.unpack_varint()

                        if uncompressed_length > 0:
                            data = zlib.decompress(packet_buff.unpack_all())
                            packet_buff = Buffer()
                            packet_buff.add(data)
                    ident = packet_buff.unpack_varint()
                    self.packet_received(packet_buff, ident)

                except BufferUnderrun:
                    raise ProtocolError("Packet is too short!")

                if packet_buff.length() > 0:
                    raise ProtocolError("Packet is too long!")

            except ProtocolError as e:
                self.protocol_error(e)
                break

            # We've read a complete packet, so reset the inactivity timeout
            self.connection_timer.restart()

    def packet_received(self, buff, ident):
        """ Dispatches packet to registered handler """

        self.log_packet("recv", ident)

        dispatched = self.dispatch((self.protocol_mode, ident), buff)

        if not dispatched:
            self.packet_unhandled(buff, ident)

    def packet_unhandled(self, buff, ident):
        """Called when a packet has no registered handler"""

        buff.discard()

    def send_packet(self, ident, data=""):
        """ Sends a packet """

        if self.closed:
            return

        self.log_packet("send", ident)

        # Prepend ident
        data = Buffer.pack_varint(ident) + data

        if self.compression_enabled:
            # Compress data and prepend uncompressed data length
            if len(data) >= self.compression_threshold:
                data = Buffer.pack_varint(len(data)) + zlib.compress(data)
            else:
                data = Buffer.pack_varint(0) + data

        # Prepend packet length
        data = self.buff_type.pack_varint(len(data)) + data

        # Encrypt
        data = self.cipher.encrypt(data)

        # Send
        self.transport.write(data)

class Factory(protocol.Factory, object):
    protocol = Protocol
    buff_type = Buffer
    log_level = logging.INFO
    connection_timeout = 30
    auth_timeout = 30

    protocol_versions = {
        4:  "1.7.4",
        5:  "1.7.10",
        47: "1.8"
    }

    def buildProtocol(self, addr):
        return self.protocol(self, addr)

    def run(self):
        reactor.run()

    def stop(self):
        reactor.stop()