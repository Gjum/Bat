import re
from twisted.internet.protocol import ReconnectingClientFactory

class BotProtocol(ClientProtocol):


class BotFactory(ClientFactory, ReconnectingClientFactory):
    protocol = BotProtocol

    def buildProtocol(self, addr):
        self.resetDelay()
        return ClientFactory.buildProtocol(self, addr)
