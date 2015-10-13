# TODO:
# tab complete, also using words from log
# inventory window
# simple! map window
# - blocks
# - terrain
# - entities
import curses
import logging
import sys
import time

from collections import namedtuple
from spockbot import default_handler
from spockbot.mcdata.constants import (
    GM_ADVENTURE, GM_CREATIVE, GM_SPECTATOR, GM_SURVIVAL)
from spockbot.plugins.base import PluginBase, pl_announce

logger = logging.getLogger('spockbot')

PROMPT = '> '

alnum = list(map(chr, range(ord('a'), ord('z') + 1)))
alnum += list(map(chr, range(ord('A'), ord('Z') + 1)))
alnum += list(map(str, range(10)))

Record = namedtuple('Record', 'seconds levelname message')


def draw_bar(val, width, c_full, c_empty=''):
    return (c_full * int(val)).ljust(int(width), c_empty)


def nice_log_text(record):
    t, levelname, message = record
    asctime = time.strftime('%H:%M:%S', time.localtime(t))
    return '%(asctime)s [%(levelname)s] %(message)s' % locals()


def break_line(line, cols, indent='  '):
    if '\n' in line:
        line_parts = []
        for line in line.split('\n'):
            line_parts.extend(break_line(line, cols, indent))
        return line_parts

    # TODO break at space/special chars?
    less_cols = cols - len(indent)
    # do not indent first line part
    line_parts, line = [line[:cols]], line[cols:]
    while line:
        line_part, line = line[:less_cols], line[less_cols:]
        line_parts.append(indent + line_part)
    return line_parts


class CursesLogHandler(logging.Handler):
    def __init__(self, screen):
        logging.Handler.__init__(self)
        self.screen = screen

    def emit(self, record):
        self.screen.add_log_record(record)


@pl_announce('Curses')
class CursesPlugin(PluginBase):
    requires = ('ClientInfo', 'Entities', 'Event')
    events = {'event_tick': 'tick'}
    events.update({e: 'kill' for e in (
        'event_kill', 'net_disconnect', 'auth_login_error')})

    def __init__(self, ploader, settings):
        super().__init__(ploader, settings)
        self.set_uncaught_exc_handler()
        curses_log_handler = CursesLogHandler(self)
        logger.addHandler(curses_log_handler)
        logger.handlers.remove(default_handler)
        logger.setLevel(logging.DEBUG)

        self.status_text = 'SpockBot'

        self.log_msgs = []
        self._log_index = 0  # used via property to auto-set redraw_lines
        self.log_start_new = 0

        self.commands = []
        self.commands_index = 0
        self.cmd_start_new = 0
        self._command = ''  # used via property to auto-set redraw_command
        self._cursor_pos = 0  # used via property to auto-set redraw_command

        self.redraw_lines = True
        self.redraw_command = True

        # setup screen
        self.stdscr = curses.initscr()
        curses.cbreak()
        curses.noecho()
        self.stdscr.nodelay(1)  # make input calls non-blocking
        self.stdscr.keypad(1)  # make curses interpret some escape sequeces
        curses.curs_set(1)  # show the text cursor

        self.rows, self.cols = self.stdscr.getmaxyx()

        curses.start_color()
        self.colors = {
            'status': (curses.COLOR_BLACK, curses.COLOR_BLUE),
            'CRITICAL': (curses.COLOR_BLACK, curses.COLOR_RED),
            'ERROR': (curses.COLOR_WHITE, curses.COLOR_RED),
            'WARNING': (curses.COLOR_BLACK, curses.COLOR_YELLOW),
            'INFO': (curses.COLOR_WHITE, curses.COLOR_BLACK),
            'DEBUG': (curses.COLOR_BLUE, curses.COLOR_BLACK),
        }
        for i, (key, (fg, bg)) in enumerate(self.colors.items()):
            color_num = i + 1
            curses.init_pair(color_num, fg, bg)
            self.colors[key] = curses.color_pair(color_num)

        self.redraw()

        try:  # if bat.cmds exists, read previous commands
            with open('bat.cmds', 'r') as f:
                for line in f:
                    self.commands.append(line[:-1])
        except FileNotFoundError:
            pass
        self.commands_index = len(self.commands)
        self.cmd_start_new = len(self.commands)

        # TODO restore previous logs?

        with open('bat.log', 'a') as f:
            f.write(time.strftime('\n===== %Y-%m-%d %H:%M:%S =====\n\n'))

    def tick(self, *args):
        self.read_input()
        self.redraw()

    def kill(self, *args):
        """ Reset terminal settings. """
        self.stdscr.keypad(0)
        curses.nocbreak()
        curses.echo()
        curses.endwin()

        self.write_logs()

        with open('bat.cmds', 'a') as f:
            for cmd in self.commands[self.cmd_start_new:]:
                f.write(cmd + '\n')

    def write_logs(self):
        with open('bat.log', 'a') as f:
            for record in self.log_msgs[self.log_start_new:]:
                f.write(nice_log_text(record))
                f.write('\n')
        self.log_start_new = len(self.log_msgs)

    def add_log_record(self, rec):
        """ add a line to the internal list of lines"""
        record = Record(rec.created, rec.levelname, rec.msg % rec.args)
        self.log_msgs.append(record)
        if self.log_index != 0:  # do not scroll when not at bottom of log
            self.log_index += 1  # TODO calculate depending on split lines
        self.redraw_lines = True
        self.redraw()

        if len(self.log_msgs) > self.log_start_new + 100:
            # write some lines now, so we do not write all at once at the end
            self.write_logs()

    def execute_command(self):
        command, *args = self.command.split(' ')
        logger.debug("[Command] %s Args: %s", command, args)
        self.event.emit('cmd', {'cmd': command, 'args': args})
        self.event.emit('cmd_%s' % command, {'args': args})

    def update_status_text(self):
        gm2string = {
            GM_CREATIVE: 'Creative',
            GM_SURVIVAL: 'Survival',
            GM_ADVENTURE: 'Adventure',
            GM_SPECTATOR: 'Spectator',
        }
        c = self.clientinfo

        pos_str = '(%.1f %.1f %.1f)' % tuple(c.position)
        gm_str = gm2string[c.game_info.gamemode]
        health_bar = draw_bar(c.health.health / 2, 10, '♥', '♡')
        food_bar   = draw_bar(c.health.food   / 2, 10, '➷', '.')
        num_entities = len(self.entities.entities)
        self.status_text = ' %s %s %s %s %s E:%s' % (
            c.name, pos_str, gm_str, health_bar, food_bar, num_entities)

    def redraw(self):
        if self.redraw_lines:
            # logger.debug('Redraw')
            self.redraw_lines = False

            # updates most of the screen anyways, so just update all of it
            self.stdscr.clear()
            self.redraw_command = True

            # TODO rework scrolling and use understandable indices
            i = -self.log_index
            for record in reversed(self.log_msgs):
                color = self.colors[record.levelname]
                line = nice_log_text(record)
                line_parts = break_line(line, self.cols)
                try:
                    for line_part in reversed(line_parts):
                        ypos = self.rows - 3 - i
                        if 0 <= ypos < self.rows - 2:  # line is visible
                            self.stdscr.addstr(ypos, 0, line_part, color)
                        i += 1
                except curses.error:
                    break

        if self.redraw_command:
            text = (PROMPT + self.command).ljust(self.cols - 1)
            try:
                self.stdscr.addstr(self.rows - 1, 0, text)
            except curses.error:
                pass

        # always redraw status
        self.update_status_text()
        text = self.status_text[:self.cols].ljust(self.cols)
        try:
            self.stdscr.addstr(self.rows - 2, 0, text, self.colors['status'])
        except curses.error:
            pass

        try:
            self.stdscr.move(self.rows - 1, self.cursor_pos + len(PROMPT))
        except curses.error:
            return
        if self.stdscr.is_wintouched():
            self.stdscr.refresh()

    def read_input(self):
        c = self.stdscr.getch()

        if c == curses.KEY_RESIZE:
            self.rows, self.cols = self.stdscr.getmaxyx()
            # xxx recalc split lines
            self.redraw_lines = True
            self.redraw_command = True

        # scroll logs
        elif c == curses.KEY_PPAGE:  # page up
            self.log_index += self.rows - 3
            self.log_index = min(len(self.log_msgs) - self.rows + 2, self.log_index)
        elif c == curses.KEY_NPAGE:  # page down
            self.log_index -= self.rows - 3
            self.log_index = max(0, self.log_index)

        # move cursor in command line
        elif c == curses.KEY_HOME:
            self.cursor_pos = 0
        elif c == curses.KEY_END:
            self.cursor_pos = len(self.command)

        elif c == curses.KEY_LEFT:
            self.cursor_pos = max(self.cursor_pos - 1, 0)
        elif c == curses.KEY_RIGHT:
            self.cursor_pos = min(self.cursor_pos + 1, len(self.command))

        elif c == 547:  # ctrl+left
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
                while self.cursor_pos >= 0 \
                        and self.command[self.cursor_pos] not in alnum:
                    self.cursor_pos -= 1
                while self.cursor_pos >= 0 \
                        and self.command[self.cursor_pos] in alnum:
                    self.cursor_pos -= 1
                self.cursor_pos += 1
        elif c == 562:  # ctrl+right
            if self.cursor_pos < len(self.command):
                self.cursor_pos += 1
                while self.cursor_pos < len(self.command) \
                        and self.command[self.cursor_pos] not in alnum:
                    self.cursor_pos += 1
                while self.cursor_pos < len(self.command) \
                        and self.command[self.cursor_pos] in alnum:
                    self.cursor_pos += 1

        # replace current command
        elif c == curses.KEY_UP:
            if self.commands_index > 0:
                self.commands_index -= 1
                self.command = self.commands[self.commands_index]
            self.cursor_pos = len(self.command)
        elif c == curses.KEY_DOWN:
            if self.commands_index + 1 < len(self.commands):
                self.commands_index += 1
                self.command = self.commands[self.commands_index]
            else:  # clear current command
                self.commands_index = len(self.commands)
                self.command = ''
            self.cursor_pos = len(self.command)

        # run current command
        elif c == curses.KEY_ENTER or c == 10:
            if self.command:
                self.execute_command()
                if self.command in self.commands[-5:]:  # remove duplicates
                    i = list(reversed(self.commands[-5:])).index(self.command)
                    del self.commands[-i - 1]
                self.commands.append(self.command)
            self.commands_index = len(self.commands)
            self.command = ''
            self.cursor_pos = 0
            self.log_index = 0

        # modify current command
        elif c == curses.KEY_BACKSPACE or c == 127:
            if self.command and self.cursor_pos > 0:
                self.command = self.command[:self.cursor_pos - 1] \
                               + self.command[self.cursor_pos:]
                self.cursor_pos -= 1

        elif c == curses.KEY_DC:  # DEL
            if self.command and self.cursor_pos > 0:
                self.command = self.command[:self.cursor_pos] \
                               + self.command[self.cursor_pos + 1:]

        # TODO ctrl+del (512), ctrl+backspace (?)

        elif ord(' ') <= c < 127:  # write printable char
            if len(self.command) == self.cols - len(PROMPT) - 2:
                return  # TODO command line too short for command
            # try:
            self.command = self.command[:self.cursor_pos] \
                + chr(c) + self.command[self.cursor_pos:]
            self.cursor_pos += 1
            # except ValueError:
            #     pass

        else:  # key ignored xxx unneeded
            if c != -1:
                logger.debug('Key ignored %s', c)

    @property
    def log_index(self):
        return self._log_index

    @log_index.setter
    def log_index(self, value):
        self._log_index = value
        self.redraw_lines = True

    @property
    def command(self):
        return self._command

    @command.setter
    def command(self, value):
        self._command = value
        self.cursor_pos = min(self.cursor_pos, len(self._command) + 1)
        self.redraw_command = True

    @property
    def cursor_pos(self):
        return self._cursor_pos

    @cursor_pos.setter
    def cursor_pos(self, value):
        self._cursor_pos = value
        self.redraw_command = True

    # try exiting curses and restore console before printing stack and crashing
    def set_uncaught_exc_handler(self):
        """ Call this function to setup the `sys.excepthook` to exit curses and
        restore the terminal before printing the exception stack trace. This way
        your application does not mess up the users terminal if it crashes. (And
        you can use assertions for debugging, etc...)"""
        def handle(exec_type, exec_value, exec_traceback):
            try:
                self.kill()
            except:
                pass
            sys.__excepthook__(exec_type, exec_value, exec_traceback)

        sys.excepthook = handle
