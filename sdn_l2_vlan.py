from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto.ether import ETH_TYPE_8021Q
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import vlan
from ryu.lib.packet import ether_types

from vlan_set import vlans_set

class sdn_l2_vlan(app_manager.RyuApp):

	OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

	def __init__(self, *args, **kwargs):
		super(sdn_l2_vlan, self).__init__(*args, **kwargs)
		self.mac_to_port = {}
		vlans = vlans_set().vlans
		self.vlan_hosts = vlans['hosts']
		self.trunks = vlans['trunks']
		

	def _add_flow(self, datapath, match=None, inst=[], table=0, priority=32768,buffer_id=0xffffffff):
		
		mod = datapath.ofproto_parser.OFPFlowMod(
			datapath=datapath, cookie=0, cookie_mask=0, table_id=table,
			command=datapath.ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
			priority=priority, buffer_id=buffer_id,
			out_port=datapath.ofproto.OFPP_ANY, out_group=datapath.ofproto.OFPG_ANY,
			flags=0, match=match, instructions=inst)

		datapath.send_msg(mod)

	def _del_flow(self, datapath, match, table):
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser

		mod = parser.OFPFlowMod(datapath=datapath,command=ofproto.OFPFC_DELETE,
								out_port=ofproto.OFPP_ANY,out_group=ofproto.OFPG_ANY,
								match=match)
		datapath.send_msg(mod)

	@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def switch_features_handler(self, ev):
		datapath = ev.msg.datapath
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser
		

		# filter datapath
		if datapath.id not in self.trunks:
			print "The datapath is not in the vlan_set."
			return

		self.mac_to_port.setdefault(datapath.id, {})
		
		the_datapath_trunks = self.trunks[datapath.id]
 
		if the_datapath_trunks is []:
			print "This set of datapath doesn't have trunk."
			return


		# table 0
		# 0.1.pass the filter of table 0
		table0_match = None
		goto_table_1_action = parser.OFPInstructionGotoTable(table_id=1)
		table0_inst = [goto_table_1_action]
		self._add_flow(datapath=datapath, match=table0_match , inst=table0_inst, priority=0, table=0)

		# table 1
		# 1.1.let the trunk pass to table 2
		for the_datapath_trunk in the_datapath_trunks:
			table1_match = parser.OFPMatch(in_port=the_datapath_trunk)
			table1_inst = [parser.OFPInstructionGotoTable(table_id=2)]
			self._add_flow(datapath=datapath, match=table1_match, inst=table1_inst, priority=99, table=1)			

		# table 2(Like table 2,3,4 of OVS.)
		# 2.1 trigger packect-in to mac learning
		table2_match = None
		table2_trigger_peckect_in_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,ofproto.OFPCML_NO_BUFFER)])
		table2_inst = [table2_trigger_peckect_in_action]
		self._add_flow(datapath=datapath, match=table2_match, inst=table2_inst, priority=0, table=2)

	@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
	def _packet_in_handler(self, ev):

		msg = ev.msg
		datapath = msg.datapath
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser
		in_port = msg.match['in_port']
		
		# find the trunk

		the_datapath_trunks = self.trunks[datapath.id];

		# packet detail

		pkt = packet.Packet(msg.data)
		eth = pkt.get_protocols(ethernet.ethernet)[0]
		eth_vlan = pkt.get_protocols(vlan.vlan)

		if eth.ethertype == ether_types.ETH_TYPE_LLDP:
			return
		
		dst = eth.dst
		src = eth.src

		dpid = datapath.id

		#find vlan

		if not src in self.vlan_hosts:
			if eth_vlan == []:
				return

		self.logger.info("packet in %s %s %s %s %s", dpid, src, dst, in_port, eth_vlan)

		if not in_port in self.trunks[dpid]:
			# add self into the flow
			self.mac_to_port[dpid][src] = in_port
			table1_match = parser.OFPMatch(eth_src=src,vlan_vid=0x0000)
			table1_push_vlan_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,[parser.OFPActionPushVlan(ETH_TYPE_8021Q),
																							    parser.OFPActionSetField(vlan_vid=self.vlan_hosts[src])])
			table1_inst = [table1_push_vlan_action,
						   parser.OFPInstructionGotoTable(table_id=2)]

			self._add_flow(datapath=datapath, match=table1_match,inst=table1_inst, priority=99,table=1)
			
			table2_match = parser.OFPMatch(eth_dst=src,vlan_vid=0x1000 | self.vlan_hosts[src])
			goto_the_port_actions = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
															[parser.OFPActionPopVlan(ETH_TYPE_8021Q),
															parser.OFPActionOutput(in_port)])
			table2_inst = [goto_the_port_actions]

			for the_datapath_trunk in self.trunks[datapath.id]:
				table0_match = parser.OFPMatch(in_port=the_datapath_trunk,eth_src=src)
				drop_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,[])
				table0_inst = [drop_action]
				self._add_flow(datapath=datapath, match=table0_match,inst= table0_inst, table=0)
		
			self._add_flow(datapath=datapath, match=table2_match, inst=table2_inst, priority=99, table=2)
		
		out_action = []

		if dst in self.mac_to_port[dpid]:
			"""drop"""
			return
		else:
			if dst != 'ff:ff:ff:ff:ff:ff':
				if dst in self.vlan_hosts:
					if self.vlan_hosts[src] != self.vlan_hosts[dst]:
						"""wrong"""
						return
					else:
						to_trunks_tag = False
						for dp in self.mac_to_port:
							if dst in self.mac_to_port[dp]:
								to_trunks_tag = True
								for the_datapath_trunk in self.trunks[datapath.id]:
									if the_datapath_trunk != in_port:
										out_action.append(parser.OFPActionOutput(the_datapath_trunk))
						
						if not to_trunks_tag:
							return
				else:
					return
			else:	
				out_port = ofproto.OFPP_FLOOD
				out_action = [parser.OFPActionPopVlan(ETH_TYPE_8021Q),parser.OFPActionOutput(out_port)]
			
		
		data = None
		if msg.buffer_id == ofproto.OFP_NO_BUFFER:
			data = msg.data

		out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=out_action, data=data)
		datapath.send_msg(out)

	@set_ev_cls(ofp_event.EventOFPPortStateChange, MAIN_DISPATCHER)
	def port_state_change_handler(self, ev):

		datapath = ev.datapath
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser

		change_port = ev.port_no

		del_mac = None
		try:
			for host in self.mac_to_port[datapath.id]:
				if self.mac_to_port[datapath.id][host] == change_port:
					print self.mac_to_port
					table0_match = parser.OFPMatch(eth_src=host)
					self._del_flow(datapath=datapath,match=table0_match,table=0)
					table1_match = parser.OFPMatch(eth_src=host)
					self._del_flow(datapath=datapath,match=table1_match,table=1)
					table2_match = parser.OFPMatch(eth_dst=host)
					self._del_flow(datapath=datapath,match=table2_match,table=2)					
					del_mac = host
					break
		except Exception, e:
			raise e

		if del_mac != None:
			del self.mac_to_port[datapath.id][del_mac]
			print self.mac_to_port
