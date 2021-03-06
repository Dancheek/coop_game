print('game initialising...')
from sys import exit
from time import time as sys_time
from PodSixNet.Connection import connection
from socket import gethostname, gethostbyname
from configparser import ConfigParser
import pygame

from client import Client
from fov import get_fov, line
import image
import text_input
import loader
import api
import tile
from object import Player
import world
import gui

BG_COLOR = (37, 37, 37)
EMPTY_COLOR = (50, 50, 50)
#YELLOW = (255, 255, 0)
#RED = (255, 50, 70)

#RED = (234, 22, 55)
#BLUE = (23, 95, 232)
#YELLOW = (241, 219, 23)
#CYAN = (25, 208, 148)
#PINK = (238, 122, 167)
#VIOLET = (165, 53, 147)

HP_COLOR = (243, 16, 76)
MP_COLOR = (15, 121, 222)
AP_COLOR = (243, 205, 48)

FIRE_COLOR = (225, 106, 0)
FREEZE_COLOR = (0, 148, 255)

TILE_WIDTH = 32

pygame.display.init()
pygame.display.set_caption("Tile game")

SCREEN_SIZE = (800, 800)
FULL_SCREEN_SIZE = (pygame.display.Info().current_w,
					pygame.display.Info().current_h)

screen_size = SCREEN_SIZE

screen_center_x = screen_size[0] // 2
screen_center_y = screen_size[1] // 2

EMPTY_TILE = 0
WALL_TILE = 1
FIRE_MAGIC = 2
FREEZE_MAGIC = 3
MAGIC_COLORS = {FIRE_MAGIC: FIRE_COLOR,
				FREEZE_MAGIC: FREEZE_COLOR}

pygame.font.init()
font = pygame.font.SysFont("consolas", 20)
DIRECTIONS = ((0, -1), (-1, 0), (0, 1), (1, 0))


class Game:
	def __init__(self):
		global screen
		screen = pygame.display.set_mode(screen_size)
		#pygame.mouse.set_cursor((8, 8), (4, 4), (0, 0, 0, 0, 0, 0, 0, 0), (0, 0, 60, 60, 60, 60, 0, 0))
		self.is_fullscreen = False

		api.screen = screen
		api.game = self
		api.send_message = self.add_message
		api.send_message_to_all = self.add_message
		api.exec_chat_command = self.exec_chat_command

		self.connected = False
		self.connecting = False

		self.debug_screen_active = False

		self.player = Player(0, 0)
		self.player.uuid = '00000000-0000-0000-0000-000000000000'

		self.read_config()

		self.d_x = 0
		self.d_y = 0

		self.m_tile_x = 0
		self.m_tile_y = 0

		self.images = api.images

		# TODO сделать нормальный hud
		self.bars = {}
		self.bar_width = 60
		self.bar_height = 16
		self.bar_sep = 28
		self.bar_x_offset = 12
		self.bar_y_offset = 12

		self.tile_classes = api.tile_classes
		self.object_classes = api.object_classes
		self.chat_commands = api.chat_commands

		self.chat_commands.update({
			'c': self.command_connect,
			'q': self.command_leave,
			'exit': self.command_exit,
			'nick': self.command_nickname,
			'help': self.command_help,
			'load_world': self.command_load_world,
			'save_world': self.command_save_world
		})

		self.forms = api.forms

		self.magic = FIRE_MAGIC
		self.clock = pygame.time.Clock()
		self.text_input = text_input.TextInput(font)
		self.state = 'normal'

		self.messages = []
		self.messages_on_screen = 20
		self.message_show_from = 0

		self.fov_radius = 12
		self.install_mods()

		self.load_world('default_world')

		self.add_message('press ENTER to open chat', color=api.YELLOW)
		self.add_message('============= COMMANDS =============')
		self.add_message('/c <ip>          - connect to server', color=api.GREY)
		self.add_message('/q               - abort connection', color=api.GREY)
		self.add_message('/nick <nickname> - change nickname', color=api.GREY)
		self.add_message('/exit            - exit from game', color=api.GREY)
		self.add_message('/help            - available commands', color=api.GREY)
		self.add_message('====================================')

		self.current_form = None

	def toggle_fullscreen(self):
		global screen
		global screen_size
		global screen_center_x
		global screen_center_y
		if (self.is_fullscreen):
			screen_size = SCREEN_SIZE
			screen_center_x = screen_size[0] // 2
			screen_center_y = screen_size[1] // 2
			screen = pygame.display.set_mode(screen_size)
			self.is_fullscreen = False
		else:
			screen_size = FULL_SCREEN_SIZE
			screen_center_x = screen_size[0] // 2
			screen_center_y = screen_size[1] // 2
			screen = pygame.display.set_mode(screen_size, pygame.FULLSCREEN)
			self.is_fullscreen = True

	def install_mods(self):
		print("loading mods...")
		self.mods = loader.load_mods()
		for mod in self.mods:
			print("{} v.{}: {}".format(mod.name, mod.version, mod.description))
			self.player.stats.update(mod.stats)
			self.player.stats_max.update(mod.stats_max)
			self.bars.update(mod.bars)

	def read_config(self):
		config = ConfigParser()
		config.read('config')
		api.config = config
		try:
			self.player.nickname = api.config['player']['nickname']
		except KeyError:
			config['player'] = {}
			config['player']['nickname'] = 'player'
			api.save_config()

	def load_world_from_dict(self, tile_map): # from server
		self.world = world.World(tile_map)
		api.world = self.world
		self.calc_fov()

	def load_world(self, world_name): # manually
		self.world = world.load(world_name)
		api.world = self.world
		if (self.player.nickname in self.world.players):
			player_dict = self.world.players[self.player.nickname]
			self.player.from_dict(player_dict)
			self.world.objects[self.player.uuid] = self.player
		else:
			self.world.add_player(self.player)
		self.calc_fov()

	def save_world(self, world_name):
		self.world.save_as(world_name)

	def tile_to_screen(self, tile_x, tile_y, center_x=None, center_y=None):
		if (center_x == None): center_x = self.player.x
		if (center_y == None): center_y = self.player.y
		return (screen_center_x - TILE_WIDTH // 2 + (tile_x - center_x) * TILE_WIDTH,
				screen_center_y - TILE_WIDTH // 2 + (tile_y - center_y) * TILE_WIDTH)

	def screen_to_tile(self, screen_x, screen_y, center_x=None, center_y=None):
		if (center_x == None): center_x = self.player.x
		if (center_y == None): center_y = self.player.y
		return ((screen_x - screen_center_x + TILE_WIDTH // 2) // TILE_WIDTH + center_x,
				(screen_y - screen_center_y + TILE_WIDTH // 2) // TILE_WIDTH + center_y)

	def calc_fov(self):
		self.fov_map = get_fov(self.world.tile_map, self.player.x, self.player.y, self.fov_radius)

	def update_mouse_tile_pos(self):
		self.m_tile_x, self.m_tile_y = self.screen_to_tile(*pygame.mouse.get_pos())

	def add_message(self, text, color=api.WHITE, player=None):
		self.messages.append({
			'text': text,
			'color': color,
			'time': sys_time()
		})

	def set_form(self, form):
		if (self.current_form != None):
			self.current_form.reset()
		if (form == None):
			self.current_form = None
			self.state = 'normal'
			return
		self.state = 'form_opened'
		if (type(form) == str):
			self.current_form = self.forms[form]
		else:
			self.current_form = form
		self.current_form.on_open(self.player)

	# ---------- potential network interacting -----------

	def change_pos(self, d_x, d_y):
		if (self.connected):
			self.client.change_pos(d_x, d_y)
		self.player.x += d_x
		self.player.y += d_y
		self.calc_fov()
		self.update_mouse_tile_pos()

	def cast_magic(self, x, y, magic):
		if (self.connected):
			self.client.cast_magic(x, y, magic)
		else:
			self.add_message("casted: {}, x: {}, y: {}".format(magic, x, y))
		self.calc_fov()

	def send_message(self, text, color=api.WHITE):
		if (text == '/q'):
			self.exec_chat_command('q')
		elif (not self.connected and text[0] == '/'):
			self.exec_chat_command(text[1:])
		else:
			if (self.connected):
				self.client.send_message({'text': text,
										'color': color})
			else:
				self.add_message(text, color=color)

	def exec_chat_command(self, text):
		if (text.split()[0] in self.chat_commands):
			self.chat_commands[text.split()[0]](*text.split(), player=self.player)
		else:
			self.add_message('command not found: ' + text.split()[0])

	def interact(self, x, y):
		if (self.connected):
			self.client.interact(x, y)
		elif (self.world.get_tile(x, y).on_interact != None):
			self.world.get_tile(x, y).on_interact(x, y, self.world.get_tile(x, y), self.player)

	# ----------- screen rendering -----------

	def draw_debug_screen(self):
		debug_info = [
			f"FPS: {round(self.clock.get_fps()):4}",
			f"x: {self.player.x:4}",
			f'y: {self.player.y:4}',
			f'm_tile_x: {self.m_tile_x:4}',
			f'm_tile_y: {self.m_tile_y:4}',
			'=============='
		]
		if (self.world.is_outside(self.m_tile_x, self.m_tile_y)):
			debug_info.append('outside of map')
		else:
			if (self.fov_map[self.m_tile_y][self.m_tile_x]):
				debug_info.append(f'id: {self.world.get_tile(self.m_tile_x, self.m_tile_y).id}')
				debug_info.append(f'meta: {self.world.get_tile(self.m_tile_x, self.m_tile_y).meta}')
			else:
				debug_info.append('not in FOV')

		obj = self.world.get_object_by_pos(self.m_tile_x, self.m_tile_y)
		if (obj != None):
			debug_info.append('==============')
			d = obj.to_dict()
			for i in d:
				debug_info.append(f'{i}: {d[i]}')

		gui.draw_rich_text(debug_info,
							api.WHITE,
							(screen_size[0] - 10, 10),
							align_x='right',
							align_y='top')

	def draw_image(self, image_id, x, y):
		screen.blit(self.images[image_id], self.tile_to_screen(x, y))

	def draw_messages(self, lifetime=5):
		if (lifetime == None):
			for i, message in enumerate(list(reversed(self.messages))[self.message_show_from:]):
				if (i == self.messages_on_screen):
					return
				pos = (10, screen_size[1] - 50 - i*21)
				gui.fill_alpha(screen, (60, 60, 60), 0.5, rect=(*pos, 500, 21))
				screen.blit(font.render(message['text'], 1, message['color']), pos)
		else:
			for i, message in enumerate(reversed(self.messages)):
				if (i == self.messages_on_screen):
					return
				if (sys_time() - message['time'] < lifetime):
					pos = (10, screen_size[1] - 50 - i*21)
					gui.fill_alpha(screen, (60, 60, 60), 0.5, rect=(*pos, 500, 21))
					screen.blit(font.render(message['text'], 1, message['color']), pos)

	def draw_stats(self):
		for bar, stat_name in enumerate(self.bars):
			for bar_max_value in range(self.bars[stat_name]['max']):
				if (bar_max_value < self.player.get_stat(stat_name)):
					screen.fill(self.bars[stat_name]['color'], (self.bar_x_offset + bar_max_value * self.bar_width, \
																self.bar_y_offset + self.bar_sep * bar, \
																self.bar_width, self.bar_height))
				else:
					screen.fill(EMPTY_COLOR, (self.bar_x_offset + bar_max_value * self.bar_width, \
												self.bar_y_offset + self.bar_sep * bar, \
												self.bar_width, self.bar_height))

	def draw_objects(self):
		for obj in self.world.objects:
			if (obj != self.player.uuid and self.fov_map[self.world.objects[obj].y][self.world.objects[obj].x]):
				self.draw_image(self.world.objects[obj].image, self.world.objects[obj].x, self.world.objects[obj].y)
		screen.blit(self.images['default:player'], (screen_center_x - TILE_WIDTH // 2, screen_center_y - TILE_WIDTH // 2))


	def draw_tile_map(self):
		for y in range(self.world.height):
			for x in range(self.world.width):
				if (self.fov_map[y][x]):
					self.draw_image(self.world.get_tile(x, y).image, x, y)

	# --------------- main loop ----------------

	def main(self):
		api.delta_time = self.clock.tick(60)
		screen.fill(BG_COLOR)

		if (self.d_x != 0 or self.d_y != 0):
			new_x = self.player.x + self.d_x
			new_y = self.player.y + self.d_y
			if (not self.world.is_outside(new_x, new_y) and self.player.get_stat('active')):
				new_tile = self.world.get_tile(new_x, new_y)

				if (new_tile.on_try_to_step != None):
					new_tile.on_try_to_step(new_x, new_y, new_tile, self.player)

				if (not new_tile.is_wall):
					self.change_pos(self.d_x, self.d_y)

					if (new_tile.on_step != None):
						new_tile.on_step(new_x, new_y, new_tile, self.player)
			self.d_x, self.d_y = 0, 0

		self.world.objects_update()

		self.draw_tile_map()
		self.draw_objects()
		if (self.state == 'normal'):
			self.draw_image('default:selection', self.m_tile_x, self.m_tile_y)

		if (self.debug_screen_active):
			self.draw_debug_screen()

		self.draw_stats()

		if (self.state == 'chat'): self.draw_messages(lifetime=None)
		else: self.draw_messages()

		if (self.state == 'chat'):
			screen.blit(self.text_input.render(), (10, screen_size[1] - 29))

		elif (self.state == 'form_opened'):
			self.current_form.update()
			self.current_form.draw()

		pygame.display.flip()

	# ------------- events handling -------------

	def handle(self, events):
		keys_pressed = pygame.key.get_pressed()
		self.update_mouse_tile_pos()

		for e in events:
			if (e.type == pygame.QUIT):
				exit()

			if (e.type == pygame.KEYDOWN):
				if (e.key == pygame.K_F4 and pygame.key.get_mods() & pygame.KMOD_ALT):
					exit()
				if (e.key == pygame.K_F11):
					self.toggle_fullscreen()

		if (self.state == 'chat'):
			self.text_input.update(events)
			for e in events:
				if (e.type == pygame.MOUSEBUTTONDOWN):
					if (e.button == 4): # scroll up
						if (len(self.messages) > self.messages_on_screen and \
							self.message_show_from + self.messages_on_screen < len(self.messages)):
								self.message_show_from += 1
					if (e.button == 5): # scroll down
						if (len(self.messages) > self.messages_on_screen and \
							self.message_show_from > 0):
								self.message_show_from -= 1

				if (e.type == pygame.KEYDOWN):
					if (e.key == pygame.K_TAB):
						self.text_input.try_autocomplete(self.chat_commands)
					if (e.key == pygame.K_RETURN):
						text = self.text_input.get_text()
						if (text == ''):
							self.state = 'normal'
						else:
							self.send_message(text)
							self.text_input.clear()

					if (e.key == pygame.K_ESCAPE):
						self.state = 'normal'

		elif (self.state == 'form_opened'):
			self.current_form.handle(events)
			for e in events:
				if (e.type == pygame.KEYDOWN):
					if (e.key == pygame.K_TAB):
						self.state = 'normal'
					if (e.key == pygame.K_ESCAPE):
						self.state = 'normal'

		elif (self.state == 'normal'):
			for e in events:
				if (e.type == pygame.MOUSEBUTTONDOWN):
					if (e.button == 1): # LMB
						if (not self.world.is_outside(self.m_tile_x, self.m_tile_y) and \
							self.fov_map[self.m_tile_y][self.m_tile_x]):
								self.cast_magic(self.m_tile_x, self.m_tile_y, self.magic)
					if (e.button == 3): # RMB
						if (not self.world.is_outside(self.m_tile_x, self.m_tile_y)):
							self.interact(self.m_tile_x, self.m_tile_y)
							self.calc_fov()

				if (e.type == pygame.MOUSEMOTION):
					if (e.buttons[0] == 1):
						pass # some drag'n'drop

				if (e.type == pygame.KEYDOWN):
					if (e.key == pygame.K_ESCAPE):
						self.set_form('default:escape_menu')
					if (e.key == pygame.K_F3):
						self.debug_screen_active = not self.debug_screen_active
					if (e.key == pygame.K_TAB):
						self.set_form('default:player_menu_form')
					if (e.key == pygame.K_RETURN):
						self.state = 'chat'
					if (e.key == pygame.K_SLASH):
						self.state = 'chat'
						self.text_input.text = '/'
						self.text_input.cursor_pos = 1
					if (e.key == pygame.K_w):
						self.d_x, self.d_y = DIRECTIONS[0]
					if (e.key == pygame.K_a):
						self.d_x, self.d_y = DIRECTIONS[1]
					if (e.key == pygame.K_s):
						self.d_x, self.d_y = DIRECTIONS[2]
					if (e.key == pygame.K_d):
						self.d_x, self.d_y = DIRECTIONS[3]
					if (e.key == pygame.K_1):
						self.magic = FIRE_MAGIC
					if (e.key == pygame.K_2):
						self.magic = FREEZE_MAGIC


	# ------------ network --------------

	def connect(self, host, port):
		if (not self.connected):
			self.send_message(f'!> connecting to {host}:{port}...', color=api.YELLOW)
			self.client = Client(self, host, port)
			self.connecting = True

	def disconnect(self):
		if (self.connecting):
			self.connecting = False
			self.add_message('!> aborted', color=api.RED)
		elif (self.connected):
			self.connected = False
			self.client.connection.Close()
			self.load_world('default_world')
			self.world.objects[self.player.uuid] = self.player
			self.calc_fov()
			self.add_message('!> disconnected from server', color=api.YELLOW)

	def on_connect(self):
		self.send_message('!> connected', color=api.YELLOW)
		self.connecting = False
		self.connected = True

	def on_disconnect(self):
		self.connecting = False
		self.connected = False
		self.add_message('!> disconnected', color=api.YELLOW)
		self.load_world('default_world')

	# ------------- chat commands --------------

	def command_connect(self, *args, player=None):
		if (len(args) == 1):
			self.connect(g_localhost, g_port)
		elif (len(args) == 2):
			self.connect(args[1], g_port)
		elif (len(args) == 3):
			if (not args[2].isdigit()):
				self.add_message('port must be a number', color=api.RED)
			else:
				self.connect(args[1], int(args[2]))
		else:
			self.add_message('Usage: /c <host> <port>', color=api.RED)

	def command_exit(self, *args, player=None):
		exit()

	def command_help(self, *args, player=None):
		self.add_message('Available commands:')
		for command in self.chat_commands:
			self.add_message(command)

	def command_leave(self, *args, player=None):
		if (self.connecting or self.connected):
			self.disconnect()

	def command_nickname(self, *args, player=None):
		if (len(args) == 2):
			self.player.nickname = args[1]
			self.add_message(f'Your nickname - "{self.player.nickname}"')
			api.config['player']['nickname'] = args[1]
			api.save_config()
		else:
			self.add_message(f'Your nickname - "{self.player.nickname}"')
			self.add_message('Usage: /nick <new nickname>', color=api.RED)

	def command_load_world(self, *args, player=None):
		if (len(args) != 2):
			api.send_message('Usage: /load_world <world name>', color=api.RED)
		else:
			api.game.load_world(args[1])
			api.send_message(f'World "{args[1]}" loaded', color=api.YELLOW)

	def command_save_world(self, *args, player=None):
		if (len(args) != 2):
			api.send_message('Usage: /save_world <world name>', color=api.RED)
		else:
			api.game.save_world(args[1])
			api.send_message(f'World saved as "{args[1]}"', color=api.YELLOW)


g_localhost = gethostbyname(gethostname())
g_port = 40327
game = Game()
while (True):
	if (game.connecting or game.connected):
		game.client.loop()
	events = pygame.event.get()
	game.handle(events)
	for mod in game.mods:
		if (hasattr(mod, 'main')):
			mod.main(game)
	game.main()

