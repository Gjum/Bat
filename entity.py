from info import object_dict, mob_dict

class Entity:
    def __init__(self, eid=-1, e_type=-1, coords=[0,0,0], yaw=0, pitch=0, data={}, velocity=[0,0,0], head_pitch=0, head_yaw=0):
        self.eid = eid
        self.e_type = e_type
        self.coords = coords
        self.data = data
        self.yaw = yaw
        self.pitch = pitch
        self.head_pitch = head_pitch
        self.head_yaw = head_yaw
        self.velocity = velocity
        self.on_ground = False

    def move(self, coords, on_ground):
        self.coords = coords
        self.on_ground = on_ground

    def relative_move(self, delta, on_ground):
        self.coords = [o+d for o,d in zip(self.coords, delta)]
        self.on_ground = on_ground

    def look(self, yaw, pitch, on_ground):
        self.yaw = yaw
        self.pitch = pitch
        self.on_ground = on_ground

    def head_look(self, yaw):
        self.head_yaw = yaw


class EntityHandler(dict):
    """Handles all loaded entities
    Instance is a dict of entity ID -> Entity instance"""

    def __init__(self, **kwargs):
        super(EntityHandler, self).__init__(**kwargs)
        # sets of entity IDs
        self.objects = set()
        self.mobs = set()
        self.drops = set()
        self.hostiles = set()

    # TODO remove
    def __getitem__(self, eid):
        if eid not in self:
            print '[EntityHandler] ERROR Access to unregistered entity', eid, '- creating dummy entity'
            self[eid] = Entity() # create dummy entity
        return super(EntityHandler, self).__getitem__(eid)

    def add_player(self, eid, uuid='', coords=[0,0,0], yaw=0, pitch=0, data={}, item=0):
        self[eid] = Entity(eid, uuid, coords, yaw, pitch, data)
        print '[EntityHandler] Player spawned at', coords, 'with ID', eid, 'and UUID', uuid

    def add_object(self, eid, obj_type, coords, yaw=0, pitch=0, data={}):
        self[eid] = Entity(eid, obj_type, coords, yaw, pitch, data)
        self.objects.add(eid)
        if obj_type == 2: # item stack
            self.drops.add(eid)
            print '[EntityHandler]', object_dict[obj_type]["name"], 'spawned with ID', eid, 'at', coords

    def add_mob(self, eid, mob_type, coords, yaw=0, pitch=0, data={}, velocity=[0,0,0], head_pitch=0):
        self[eid] = Entity(eid, mob_type, coords, yaw, pitch, data, velocity, head_pitch)
        self.mobs.add(eid)
        is_hostile = mob_dict[mob_type]['hostile']
        if is_hostile:
            self.hostiles.add(eid)
        print '[EntityHandler]', mob_dict[mob_type]["name"], '(hostile)' if is_hostile else '(not hostile)', 'spawned with ID', eid, 'at', coords

    def remove(self, eid):
        if eid not in self:
            print '[EntityHandler] Could not remove unknown EID', eid
            return
        del self[eid]
        self.objects.discard(eid)
        self.mobs.discard(eid)
        self.drops.discard(eid)
        self.hostiles.discard(eid)
        #print '[EntityHandler] Removed', eid

