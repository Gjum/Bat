"""
Look up recipes and craft items.
"""
from collections import namedtuple, defaultdict
from math import ceil
from spock.utils import pl_announce
from bat.recipes import recipes
from bat.utils import run_task

import logging
logger = logging.getLogger('spock')

RecipeItem = namedtuple('RecipeItem', 'id meta amount')
Recipe = namedtuple('Recipe', 'result ingredients in_shape out_shape')

def reformat_item(raw, default_meta=-1):
	if isinstance(raw, dict):
		raw = raw.copy()  # do not modify arg
		if 'meta' not in raw:
			raw['meta'] = default_meta
		if 'amount' not in raw:
			raw['amount'] = 1
		return RecipeItem(**raw)
	elif isinstance(raw, list):
		return RecipeItem(raw[0], raw[1], 1)
	else: # single ID or None
		return RecipeItem(raw or -1, default_meta, 1)

def reformat_shape(shape):
	return [[reformat_item(item, -1) for item in row] for row in shape]

def to_recipe(raw):
	result = reformat_item(raw['result'], -1)
	if 'ingredients' in raw:
		ingredients = [reformat_item(item, 0) for item in raw['ingredients']]
		in_shape = out_shape = None
	else:
		in_shape = reformat_shape(raw['inShape'])
		out_shape = reformat_shape(raw['outShape']) if 'outShape' in raw else None
		ingredients = [item for row in in_shape for item in row]  # flatten
	recipe = Recipe(result, ingredients, in_shape, out_shape)
	return recipe

def iter_recipes_for(item_id, meta=-1):
	try:
		recipes_for_item = recipes[str(item_id)]
	except KeyError:
		return
	else:
		for raw in recipes_for_item:
			recipe = to_recipe(raw)
			if meta == -1 or meta == recipe.result.meta:
				yield recipe

@pl_announce('Craft')
class CraftPlugin:
	def __init__(self, ploader, settings):
		self.event = ploader.requires('Event')
		self.inventory = ploader.requires('Inventory')
		ploader.provides('Craft', self)

	def find_recipe(self, item, meta=-1):
		for matching in iter_recipes_for(item, meta):
			return matching
		return None

	def get_total_amounts_needed(self, recipe):
		totals = defaultdict(int)
		for id, meta, amount in recipe.ingredients:
			totals[(id, meta)] += amount
		return totals

	def craft(self, item=None, meta=-1, amount=1, recipe=None, callback=None):
		"""
		Starts a craft_task. Returns the recipe used for crafting.
		Either `item` or `recipe` has to be given.
		Calls callback with the result of the craft_task.
		"""
		if not recipe:
			recipe = self.find_recipe(item, meta)
		else:
			item, meta, _ = recipe.result
		if recipe:
			craft_task = self.craft_task(recipe, amount)
			run_task(craft_task, self.event, callback=callback)
		return recipe

	def craft_task(self, recipe, amount=1):
		"""
		Crafts `amount` items with `recipe`.
		Returns True if all items were crafted, False otherwise.
		(use `yield from` or `run_task(callback=cb)` to get the return value)
		"""
		if not recipe:
			logger.error('[Craft] No recipe given: %s', recipe)
			return False
		if amount <= 0:
			logger.warn('[Craft] Nothing to craft, amount=%s', amount)
			return False

		inv = self.inventory
		craft_times = int(ceil(amount / recipe.result.amount))

		try:  # check if open window supports crafting
			result_slot = inv.window.craft_result_slot
			grid_slots = inv.window.craft_grid_slots
		except AttributeError:
			logger.error('[Craft] No crafting window open :( %s', type(inv.window))
			return False
		grid_width = 3 if len(grid_slots) == 9 else 2  # TODO is there a better way?
		# TODO check recipe size against grid size
		grid_start = grid_slots[0].slot_nr
		storage_slots = inv.window.persistent_slots
		storage_start = storage_slots[0].slot_nr

		logger.info('[Craft] Checking materials for recipe: %s', recipe)
		while 1:
			for (mat_item, mat_meta), needed in self.get_total_amounts_needed(recipe).items():
				needed *= craft_times
				logger.debug('[Craft mat] Checking for %sx %s:%s', needed, mat_item, mat_meta)
				stored = inv.total_stored(mat_item, mat_meta, storage_slots)
				logger.debug('[Craft mat] %sx %s:%s stored', stored, mat_item, mat_meta)
				if needed > stored:  # need to craft a missing material
					logger.info('[Craft mat] No %s:%s found, crafting...', mat_item, mat_meta)
					mat_recipe = self.find_recipe(mat_item, mat_meta)
					if not mat_recipe:
						logger.error('[Craft] No recipe found for %s:%s', mat_item, mat_meta)
						return False
					material_crafted = yield from self.craft_task(mat_recipe, needed - stored)
					stored = inv.total_stored(mat_item, mat_meta, storage_slots)
					if not material_crafted or needed > stored:  # crafting the missing material failed
						logger.error('[Craft mat] No %s:%s crafted, aborting', mat_item, mat_meta)
						return False
					break  # check all materials again
			else:  # all materials found
				logger.debug('[Craft mat] All materials found')
				break  # while

		def put_away_or_drop():
			first_empty_slot = inv.find_slot(-1, start=storage_start)
			if first_empty_slot:
				return inv.click_slot(first_empty_slot)
			else:
				return inv.drop_slot(inv.cursor_slot, drop_stack=True)  # TODO untested

		# iterates over a recipe's shape or ingredients
		def iter_shape():
			if recipe.in_shape:
				for y, row in enumerate(recipe.in_shape):
					for x, (m_id, m_meta, m_amount) in enumerate(row):
						slot = grid_slots[x + y * grid_width]
						yield (slot, m_id, m_meta, m_amount)
			else:
				for slot, (m_id, m_meta, m_amount) in zip(grid_slots, recipe.ingredients):
					yield (slot, m_id, m_meta, m_amount)

		logger.info('[Craft] Putting materials into crafting grid...')
		for slot, mat_id, mat_meta, mat_amount in iter_shape():
			for i in range(mat_amount * craft_times):
				if inv.cursor_slot.amount < 1:
					mat_slot = inv.find_slot(mat_id, mat_meta, storage_start)
					if not mat_slot:
						logger.error('[Craft put in] No %s:%s found :(', mat_id, mat_meta)
						return False
					yield inv.click_slot(mat_slot)
				yield inv.click_slot(nr=slot, right=True)
			# done putting in that item, put away
			if inv.cursor_slot.amount > 0:
				yield put_away_or_drop()

		logger.info('[Craft] Taking crafted items from %s', result_slot)
		cursor_amt = inv.cursor_slot.amount
		crafted_amt = 0
		while crafted_amt + cursor_amt < amount:
			yield inv.click_slot(result_slot)
			# cursor amount shoud have changed, as we just clicked
			if cursor_amt == inv.cursor_slot.amount:
				# cursor full, put away
				logger.debug('[Craft take] Stack full, putting away')
				crafted_amt += cursor_amt
				yield put_away_or_drop()
			cursor_amt = inv.cursor_slot.amount
			logger.debug('[Craft take] Got %s/%s so far', crafted_amt + cursor_amt, amount)
		if inv.cursor_slot.amount > 0:
			# cursor still has items left from crafting, put away
			yield put_away_or_drop()

		logger.info('[Craft] Putting materials back')
		for grid_slot in grid_slots:
			if grid_slot.amount > 0:
				yield inv.click_slot(grid_slot)
				if inv.cursor_slot.amount > 0:
					logger.debug('[Craft back] putting back %s', grid_slot)
					yield put_away_or_drop()
		logger.info('[Craft] Done!')
		return True

