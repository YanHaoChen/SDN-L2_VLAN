import json

class vlans_set(object):
	"""docstring for vlans"""
	def __init__(self):
		super(vlans_set, self).__init__()
		self.vlans = {'trunks':{
								1:[30,40],
								2:[30,40],
								3:[30,50]
								},
					  'hosts':{
					  			'00:00:00:00:00:01':20,
					  			'00:00:00:00:00:02':20,
					  			'00:00:00:00:00:03':30,
					  			'00:00:00:00:00:04':30
					  			}
					 }