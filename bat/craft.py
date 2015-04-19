"""
Look up recipes and craft items.
"""
from collections import namedtuple, defaultdict
from math import ceil
from spock.plugins.helpers.inventory import BaseClick, INV_BUTTON_LEFT, Slot
import logging
from bat.utils import run_task

logger = logging.getLogger('spock')

RecipeItem = namedtuple('RecipeItem', 'item meta amount')
Recipe = namedtuple('Recipe', 'shape_in shape_out result')

recipes = {
	5: {
		0: Recipe([RecipeItem(17, 0, 1)],
				  [RecipeItem(-1, 0, 0)],
				  RecipeItem(5, 0, 4)),
	},
}

def recipe_valid(recipe, window):
	# TODO shapeless recipes?
	# not needed at the moment, because when we craft something,
	# we follow the shape, so there are practically no shapeless recipes
	no_match = lambda r, s: r.item != s.item_id or r.meta not in (-1, s.damage) or r.amount > s.amount
	for recipe_item, slot in zip(recipe.shape_in, window.craft_grid_slots()):
		if no_match(recipe_item, slot):
			return False
	return True

class CraftLeftClick(BaseClick):
	def __init__(self, recipe):
		self.recipe = recipe

	def get_packet(self, inv_plugin):
		slot_nr = inv_plugin.window.craft_result_slot().slot_nr
		r = self.recipe.result
		return {
			'slot': slot_nr,
			'button': INV_BUTTON_LEFT,
			'mode': 0,
			'clicked_item': Slot(None, None, r.item, r.meta, r.amount).get_dict(),
		}

	def update_output(self, result_slot):
		result_slot.item_id = self.recipe.result.item
		result_slot.damage = self.recipe.result.meta
		result_slot.amount = self.recipe.result.amount
		result_slot.nbt = None
		self.mark_dirty(result_slot)

	def apply(self, inv_plugin):
		result_slot_nr = inv_plugin.window.craft_result_slot().slot_nr
		result_slot = inv_plugin.window.slots[result_slot_nr]
		cursor = inv_plugin.cursor_slot
		if recipe_valid(self.recipe, inv_plugin.window):
			# apply crafting output
			self.update_output(result_slot)
			if not cursor:
				self.swap_slots(result_slot, cursor)
			elif result_slot.stacks_with(cursor) \
					and cursor.amount < cursor.max_amount():
				self.transfer(result_slot, cursor, result_slot.amount)
			# apply recipe once
			for rin, rout, slot in zip(
					self.recipe.shape_in,
					self.recipe.shape_out,
					inv_plugin.window.craft_grid_slots()
			):
				delta = rin.amount - rout.amount
				if delta != 0:
					slot.amount -= delta
					self.cleanup_if_empty(slot)
		# shape changed, test again
		if recipe_valid(self.recipe, inv_plugin.window):
			# restore crafting output
			self.update_output(result_slot)
		else:  # no recipe, no result
			result_slot.amount = 0
			self.cleanup_if_empty(result_slot)

class CraftPlugin:
	def __init__(self, ploader, settings):
		self.event = ploader.requires('Event')
		self.inventory = ploader.requires('Inventory')
		ploader.provides('Craft', self)

	def get_recipe(self, item, meta=-1):
		try:
			if meta == -1:
				return list(recipes[item].values())[0]
			else:
				return recipes[item][meta]
		except KeyError:
			return None

	def get_total_amounts_needed(self, recipe):
		amounts = defaultdict(int)
		for item, meta, amount in recipe.shape_in:
			amounts[(item, meta)] += amount
		return amounts

	def craft(self, item, meta=-1, amount=1, callback=None):
		recipe = self.get_recipe(item, meta)
		craft_task = self.craft_task(recipe, amount)
		run_task(craft_task, self.event, callback=callback)

	def craft_task(self, recipe, amount=1):
		inv = self.inventory
		craft_times = int(ceil(amount / recipe.result.amount))

		if not recipe:
			logger.error('[Craft] No recipe given :( %s', recipe)
			return False
		try:
			out_slot = inv.window.craft_result_slot()
			grid_slots = inv.window.craft_grid_slots()
			first_inside_craft_grid = grid_slots[0].slot_nr
			storage_start = inv.window.inventory_slots()[0].slot_nr
			# TODO check recipe size against grid size
		except AttributeError:
			logger.error('[Craft] No crafting window open :( %s', type(inv.window))
			return False

		logger.info('[Craft] Checking materials for recipe: %s', recipe)
		while 1:
			for (mat_item, mat_meta), needed in self.get_total_amounts_needed(recipe).items():
				needed *= craft_times
				logger.debug('[Craft mat] Checking for %sx %s:%s', needed, mat_item, mat_meta)
				stored = inv.total_stored(mat_item, mat_meta, inv.window.slots[storage_start:])
				logger.debug('[Craft mat] %sx %s:%s stored', stored, mat_item, mat_meta)
				if needed > stored:
					logger.info('[Craft mat] No %s:%s found, crafting...', mat_item, mat_meta)
					mat_recipe = self.get_recipe(mat_item, mat_meta)
					if not mat_recipe:
						logger.error('[Craft] No recipe found for %s:%s', mat_item, mat_meta)
						return False
					material_crafted = yield from self.craft_task(mat_recipe, needed - stored)
					if not material_crafted:
						logger.error('[Craft mat] No %s:%s crafted, aborting', mat_item, mat_meta)
						return False
					break
			else:  # all materials found
				logger.debug('[Craft mat] All materials found')
				break  # while

		def click_first_item(item, meta=-1, start=0):
			found = inv.find_item(item, meta, start)
			if found:
				yield inv.click_slot(found)
				return True
			return False

		def put_away_or_drop(start=storage_start):
			inv_has_free_space = yield from click_first_item(-1, start=start)
			if not inv_has_free_space:
				logger.debug('[Craft] Inventory full, dropping')
				yield inv.drop_item(-999, drop_stack=True)

		logger.info('[Craft] Putting materials in...')
		for grid_nr, (mat_item, mat_meta, mat_amount) in enumerate(recipe.shape_in):
			for i in range(mat_amount * craft_times):
				if inv.cursor_slot.amount < 1:
					inv_has_material = yield from click_first_item(mat_item, mat_meta, storage_start)
					if not inv_has_material:
						logger.error('[Craft put in] No %s:%s found :(', mat_item, mat_meta)
						return False
				yield inv.click_slot(grid_nr + first_inside_craft_grid, right=True)
			# done putting in that item, put away
			if inv.cursor_slot.amount > 0:
				yield from put_away_or_drop()

		logger.info('[Craft] Get crafted items from %s', out_slot)
		prev_amt = 0
		for i in range(craft_times):
			yield inv.send_click(CraftLeftClick(recipe))
			if prev_amt == inv.cursor_slot.amount:
				# stack full, put away
				logger.debug('[Craft get] Stack full, putting away')
				yield from put_away_or_drop()
			logger.debug('[Craft get] Got %s so far', prev_amt)
			prev_amt = inv.cursor_slot.amount
		if inv.cursor_slot.amount > 0:
			yield from put_away_or_drop()

		logger.info('[Craft] Putting materials back')
		for grid_nr in range(len(grid_slots)):
			yield inv.click_slot(grid_nr + first_inside_craft_grid)
			if inv.cursor_slot.amount > 0:
				logger.debug('[Craft back] non-empty %s', inv.window.slots[grid_nr + first_inside_craft_grid])
				yield from put_away_or_drop()
			else:
				logger.debug('[Craft back] empty %s', grid_nr + first_inside_craft_grid)

		logger.info('[Craft] Done!')
		return True