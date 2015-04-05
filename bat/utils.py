from math import floor
from spock.utils import Vec3

class Vec:
	def __init__(self, *args):
		self.set(*args)

	def __repr__(self):
		return 'Vec(%s)' % str(self.c)

	def get_dict(self):
		return {'x': self.c[0], 'y': self.c[1], 'z': self.c[2]}

	def set(self, *args):
		if len(args) == 0:
			args = [(0,0,0)]
		first_arg = args[0]
		if isinstance(first_arg, Vec):
			self.c = first_arg.c[:]
		elif hasattr(first_arg, 'x') and hasattr(first_arg, 'y') and hasattr(first_arg, 'z'):
			self.c = [first_arg.x, first_arg.y, first_arg.z]
		elif isinstance(first_arg, list) or isinstance(first_arg, tuple):
			self.c = first_arg[:3]  # argument is coords triple
		elif len(args) == 3:
			self.c = args[:3]  # arguments are x, y, z
		else:
			raise ValueError('Invalid args: %s', args)
		return self

	def add(self, *args):
		d = Vec(*args)
		self.c = [c + d for c, d in zip(self.c, d.c)]
		return self

	def sub(self, *args):
		d = Vec(*args)
		self.c = [c-d for c,d in zip(self.c, d.c)]
		return self

	def round(self):
		self.c = [int(floor(c)) for c in self.c]
		return self

	def center(self):
		return self.round().add(.5, .0, .5)

	def dist_sq(self, other=None):
		v = Vec(other).sub(self) if other else self
		x, y, z = v.c
		return x*x + y*y + z*z

	def x(self):
		return self.c[0]

	def y(self):
		return self.c[1]

	def z(self):
		return self.c[2]

	def override_vec3(self, v3=Vec3()):
		v3.x, v3.y, v3.z = self.c
		return v3
