from ryu.base import app_manager

# protocol
from ryu.ofproto import ofproto_v1_3

# control
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls

# parse packet
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp

# vlan set
from vlan_set import vlans_set

# bfs
import Queue

class sdn_l2_vlan(app_manager.RyuApp):
	OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
	def __init__(self, *args, **kwargs):
		super(sdn_l2_vlan, self).__init__(*args, **kwargs)
		self.switches_table = {}
		self.vlans_table = {}

		vlans_config = vlans_set().vlans

		self.switch_trunks = vlans_config["switches"]
		self.hosts = vlans_config["hosts"]

	###### other
	def find_trunk(datapath_id):
		result = []
		
		for trunk in self.switch_trunks[datapath_id]:
			result.append(trunk["port"])

		return result

	###### flow

	### add_flow

	def add_flow(self, datapath, match=None, inst=[], table=0, priority=32768, buffer_id=0xffffffff):

		mod = datapath.ofproto_parser.OFPFlowMod(
			datapath=datapath, cookie=0, cookie_mask=0, table_id=table,
			command=datapath.ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
			priority=priority, buffer_id=buffer_id,
			out_port=datapath.ofproto.OFPP_ANY, out_group=datapath.ofproto.OFPG_ANY,
			flags=0, match=match, instructions=inst)

		datapath.send_msg(mod)

	### del_flow

	def del_flow(self, datapath, match, table):

		mod = datapath.ofproto_parser.OFPFlowMod(datapath=datapath,
												command=datapath.ofproto.OFPFC_ELETE,
												out_port=datapath.ofproto.OFPP_ANY,
												out_group=ofproto.OFPG_ANY,
												match=match)

		datapath.send_msg(mod)

	###### packet

	### send_packet

	def send_packet(self, datapath, port, pkt):
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser
		pkt.serialize()
		print "packet-out:\n %s" % pkt
		data = pkt.data

		action = [parser.OFPActionOutput(port=port)]

		out = parser.OFPPacketOut(datapath=datapath,
									buffer_id=ofproto.OFP_NO_BUFFER,
									in_port=ofproto.OFPP_CONTROLLER,
									actions=action,
									data=data)
		datapath.send_msg(out)


	######  handlers of events

	### features_handler

	@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
	def switch_features_handler(self, ev):
		datapath = ev.msg.datapath
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser

		if datapath.id not in self.switch_trunks:
			print "The switch is not in the lan."
			return

		if len(self.switch_trunks[datapath.id]) == 0:
			print "The switch don't have trunk."
			return

		self.switches_table.setdefault(datapath.id,{})
		self.switches_table[datapath.id]["instance"] = datapath

		table_0_match = None
		goto_table_1_action = parser.OFPInstructionGotoTable(table_id=1)
		table_0_inst = [goto_table_1_action]
		self.add_flow(datapath=datapath, match=table_0_match, inst=table_0_inst, priority=0, table=0)

		for trunk in self.switch_trunks[datapath.id]:
			table_1_match = parser.OFPMatch(in_port=trunk["port"])
			goto_table_2_action = parser.OFPInstructionGotoTable(table_id=2)
			table_1_inst = [goto_table_2_action]
			self.add_flow(datapath=datapath, match=table_1_match, inst=table_1_inst, priority=99, table=1)

		return

	### packet_in_handler

	@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
	def packet_in_handler(self,ev):
		msg = ev.msg
		datapath = msg.datapath
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser

		port = msg.match['in_port']

		pkt = packet.Packet(data=msg.data)

		pkt_ethernet = pkt.get_protocol(ethernet.ethernet)

		if not pkt_ethernet:
			return

		# arp
		pkt_arp =pkt.get_protocol(arp.arp)

		if pkt_arp:
			self.arp_handler(datapath=datapath, port=port, pkt_ethernet=pkt_ethernet, pkt_arp=pkt_arp)

		# learning
		self.learning_handler(datapath, port, pkt)

		
		

	###### handlers of situations

	### learning
	def learning_handler(self, datapath, port, pkt):
		ofproto = datapath.ofproto
		parser = datapath.ofproto_parser

		trunks = self.find_trunk[datapath.id]
		src_vlan = -1

		pkt_ethernet = pkt.get_protocol(ethernet.ethernet)

		for host in self.hosts:
			if pkt_ethernet.src == host["MAC"]:
				src_vlan = host["VLAN_ID"]

		if not src_vlan:
			return

		if port not in trunks:
			none_vlan_tag_match = parser.OFPMatch(eth_src=pkt_ethernet.src, vlan_vid=0x0000)
			push_vlan_tag_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
																[parser.OFPActionPushVlan(ETH_TYPE_8021Q),
																parser.OFPActionSetField(vlan_vid=src_vlan)])
			goto_table_2_action = parser.OFPInstructionGotoTable(table_id=2)
			table_1_inst = [push_vlan_tag_action,goto_table_2_action]
			self.add_flow(datapath=datapath, match=none_vlan_tag_match, inst=table_1_inst, priority=99, table=1)

			src_and_vlan_match = parser.OFPMatch(eth_dst=pkt_ethernet.src, vlan_vid=0x1000 | src_vlan)
			goto_the_port_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
																[parser.OFPAcitionPopVlan(ETH_TYPE_8021Q),
																parser.OFPActionOutput(port)])
			table_2_inst = [goto_the_port_action]
			self.add_flow(datapath=datapath, match=src_and_vlan_match, inst=table_2_inst, priority=50, table=2)
			
			# path
			self.vlans_table.setdefault(src_vlan,set())

			if datapath.id not in self.vlans_table[src_vlan]:
				self.vlans_table[src_vlan].add(datapath.id)
				vlan_match = parser.OFPMatch(vlan_vid=0x1000 | src_vlan)
				output_actions = []
				for trunk in trunks:
					output_actions.append(parser.OFPActionOutput(trunk))

				out_of_switch_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,output_actions)
				trunk_inst = [out_of_switch_action]
				self.add_flow(datapath=datapath, match=vlan_match, inst=trunk_inst, priority=20, table=2)
				
				if len(self.vlans_table[src_vlan]) > 1:



	### arp
	def arp_handler(self, datapath, port, pkt_ethernet, pkt_arp):
		
		if pkt_arp.opcode != arp.ARP_REQUEST:
			return

		src_vlan = -1
		src_mac = pkt_ethernet.src
		src_ip = ""

		dst_vlan = -1
		dst_mac = ""
		dst_ip = pkt_arp.dst_ip

		#find vlan
		for host in self.hosts:
			if pkt_ethernet.src == host["MAC"]:
				src_vlan = host["VLAN_ID"]
				src_ip = host["IP"] 

			if pkt_arp.dst_ip == host["IP"]:
				dst_vlan = host["VLAN_ID"]
				dst_mac = host["MAC"]

			if src_vlan and dst_vlan:
				break

		# The dst host is not in the set.
		if not dst_vlan:
			return

		# They are not the same vlan.
		if src_vlan != dst_vlan:
			return

		pkt = packet.Packet()
		pkt.add_protocol(ethernet.ethernet(ethertype=pkt_ethernet.ethernet.ethertype,
											dst=src_mac,
											src=dst_mac))
		pkt.add_protocol(arp.arp(opcode=arp.ARP_REPLY,
									src_mac=dst_mac,
									src_ip=dst_ip,
									dst_mac=src_mac,
									dst_ip=src_ip
								)
						)
		self.send_packet(datapath, port, pkt)
