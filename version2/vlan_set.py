import json

class vlans_set(object):
	"""docstring for vlans"""
	def __init__(self):
		super(vlans_set, self).__init__()
		self.vlans = {'switches':{
								1:[{"toswitch":2,"port":30},{"toswitch":3,"port":40},{"toswitch":4,"port":50}],
								2:[{"toswitch":1,"port":30},{"toswitch":3,"port":40}],
								3:[{"toswitch":1,"port":30},{"toswitch":2,"port":40}],
								4:[{"toswitch":1,"port":30}]
								},
					  'hosts':[
					  			{"MAC":'00:00:00:00:00:01',"IP":'10.0.0.1',"VLAN_ID":20},
					  			{"MAC":'00:00:00:00:00:02',"IP":'10.0.0.2',"VLAN_ID":20},
					  			{"MAC":'00:00:00:00:00:03',"IP":'10.0.0.3',"VLAN_ID":30},
					  			{"MAC":'00:00:00:00:00:04',"IP":'10.0.0.4',"VLAN_ID":30}
					  			]
					 }