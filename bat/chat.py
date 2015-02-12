
from spock.utils import pl_announce

@pl_announce('Chat')
class ChatPlugin:
	""" Emits `chat_<sort>` event with `{name, uuid, sort, text}` on public/private chat and announcements.
	<sort> is pub, msg, or say.
	`uuid` contains dashes and is Null if not present. """

	def __init__(self, ploader, settings):
		self.event = ploader.requires('Event')
		ploader.reg_event_handler("PLAY<Chat Message", self.check_chat_for_command)

	def check_chat_for_command(self, evt, packet):
		data = packet.data
		try:
			what = str(data['json_data']['translate'])
			uuid = None
			name = data['json_data']['with'][0]
			if not isinstance(name, str): # player name is hidden informatting maze
				uuid = name['hoverEvent']['value'][5:41]
				name = name['text']
			if what == 'chat.type.text': # public chat
				sort = 'pub'
				text = str(data['json_data']['with'][1])
			elif what in ('commands.message.display.incoming', 'chat.type.announcement'): # private chat or announcement
				sort = 'say' if what == 'chat.type.announcement' else 'msg'
				text = str(''.join(data['json_data']['with'][1]['extra']))
			else:
				raise NotImplementedError('Unknown chat type: %s' % what) # catched below
		except (LookupError, TypeError, NotImplementedError): # Unknown chat type or parsing error
			# TODO maybe log debug message?
			return
		else:
			cmd_info = { 'name': name, 'uuid': uuid, 'sort': sort, 'text': text }
			self.event.emit('chat_%s' % sort, cmd_info)
