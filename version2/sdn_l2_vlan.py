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

class sdn_l2_vlan(app_manager.RyuApp):
	OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
	def __init__(self, *args, **kwargs):
		super(sdn_l2_vlan, self).__init__(*args, **kwargs)
		self.switches_table = {}
		self.vlans_table = {}

		vlans_config = vlans_set().vlans

		self.switch_trunks = vlans_config["switches"]
		self.hosts = vlans_config["hosts"]


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


	###### event handler 

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
		
		pkt_arp =pkt.get_protocol(arp.arp)

		if pkt_arp:
			print "arp dst_ip:%s" % pkt_arp.dst_ip

		return
