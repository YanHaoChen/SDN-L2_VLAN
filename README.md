# 以 RYU 實現自動化 VLAN 分配、管理

使用 RYU 對多 switch 進行自動化 VLAN 分配及管理。管理者只需要透過三項環境已知條件（VLAN 對應的主幹、主機的 MAC address 及對應 VLAN ID），即可將 VLAN 管理規則下達至 switch，自動化分配主機所屬 VLAN 及封包配送方式。

## 特性

* 以 JSON 記錄環境已知條件。（```vlan_set.py```）

* 在 switch 間有迴圈的狀況下，仍可正常運作。

* 在管轄內的 switch 中，管轄內的主機皆可任意更改使用的 port，且無須設定，可直接更動。

* 以 table 分層管理規則。（過濾、分配、學習）

## Table 轉送邏輯

```python
# table 0 (過濾)
if 由主幹進入的封包，封包的來源主機在此 switch 中:
	# 預防 switch 間迴圈問題
	drop
else:
	goto table 1

# table 1（分配）
if 來源主機的在管轄內，且無 VLAN tag:
	加入對應的 VLAN tag
	goto table 2
else:
	goto controller

# table 2（學習）
if 目的主機在此 switch 中，且 VLAN tag 正確:
	去除 VLAN tag 轉送至目的主機
else:
	goto controller
```


## 虛擬環境配置

* OpenFlow：1.3 版。
* controller：1 台。
* switch：3 台。
* host：4 台。
* VLAN 20：h1（00:00:00:00:00:01）、h2（00:00:00:00:00:02）。
* VLAN 30：h3（00:00:00:00:00:03）、h4（00:00:00:00:00:04）。
* switch 1 連接 h1（主幹：30、40）。
* switch 2 連接 h2（主幹：30、40）。
* switch 3 連接 h3 及 h4（主幹：30、50）。
* switch 間透過主幹互相連接。

### Mininet 環境（```mininet_env.py```）
```python
mininet> net
h1 h1-eth0:s1-eth1
h2 h2-eth0:s2-eth1
h3 h3-eth0:s3-eth1
h4 h4-eth0:s3-eth2
s1 lo:  s1-eth1:h1-eth0 s1-eth30:s2-eth30 s1-eth40:s3-eth50
s2 lo:  s2-eth1:h2-eth0 s2-eth30:s1-eth30 s2-eth40:s3-eth30
s3 lo:  s3-eth1:h3-eth0 s3-eth2:h4-eth0 s3-eth30:s2-eth40 s3-eth50:s1-eth40
c0
```
## 運作機制

以下將介紹各段程式的用途及設計原因。

### 初始化
載入配置狀況，並分別存放在以下兩個變數中：

* ```self.vlan_hosts```：主機的 VLAN 資訊，key 為 MAC address，value 為 VLAN ID。
* ```self.trunks```：switch 的主幹資訊，key 為 Datapath ID，value 為主幹 port Number（以陣列存放）。


```python
def __init__(self, *args, **kwargs):
...
	vlans = vlans_set().vlans
	self.vlan_hosts = vlans['hosts']
	self.trunks = vlans['trunks']
...
```

### 與 switch 連接
在與switch連接時，建立初步的規則。

* 剔除管轄外的 switch，並取出主幹，存放在```the_datapath_trunks```中。

```python
@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
def switch_features_handler(self, ev):
	...
	if datapath.id not in self.trunks:
		print "The datapath is not in the vlan_set."
		return

	the_datapath_trunks = self.trunks[datapath.id]
 
	if the_datapath_trunks is []:
		print "This set of datapath doesn't have trunk."
		return
	...
```

* 設定 table 0 的 default 處理動作（轉送至 table 1）。

```python
@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
def switch_features_handler(self, ev):
	...
	table0_match = None
	goto_table_1_action = parser.OFPInstructionGotoTable(table_id=1)
	table0_inst = [goto_table_1_action]
	self._add_flow(datapath=datapath, match=table0_match , inst=table0_inst, priority=0, table=0)
	...
```

* 設定由主幹傳入的封包在經過 table 1 時，可以直接通過，並轉送至 table 2。

```python
@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
def switch_features_handler(self, ev):
	...
	table0_match = None
	goto_table_1_action = parser.OFPInstructionGotoTable(table_id=1)
	table0_inst = [goto_table_1_action]
	self._add_flow(datapath=datapath, match=table0_match , inst=table0_inst, priority=0, table=0)
	...
```

* 設定 table 2 在收到封包後，如果沒有對應到的規則，則將封包轉送至 controller。

```python
@set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
def switch_features_handler(self, ev):
	...
	table0_match = None
	goto_table_1_action = parser.OFPInstructionGotoTable(table_id=1)
	table0_inst = [goto_table_1_action]
	self._add_flow(datapath=datapath, match=table0_match , inst=table0_inst, priority=0, table=0)
	...
```
> 此規則，並非一定要加入，因為當有封包沒有對應到任何規則時，也會自動轉往 controller。

### 有未知封包時
當有未知封包時，處理的方式及原因介紹。

* 取得封包 VLAN 資訊。

```python
@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
def _packet_in_handler(self, ev):
	...
	eth_vlan = pkt.get_protocols(vlan.vlan)
	...
```

* 過濾沒有 VLAN 的封包，但讓來源是管轄內的主機的封包通過（因有可能是 ARP 回覆或請求）。

```python
@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
def _packet_in_handler(self, ev):
	...
	if not src in self.vlan_hosts:
		if eth_vlan == []:
			return
	...
```

* 如果封包不是來自於主幹，則代表是與 switch 直接連結的主機。因此，如果主機在管轄範圍內運作邏輯如下:

```python
if 封包不是來自於主幹:
	1.將來源主機的 MAC address 當作新規則的 Match 條件（eth_src），加入 table 1 中。並設定在 Match 此規則後，加上對應的 VLAN ID。 
	2.在 table 2 中，也是加入 MAC address 當作新規則的 Match 條件，但這次換做是 eth_dst，並加入 VLAN ID 也當作其中一個 Match 條件。目的是為了學習此規則，如往後有目的地是此主機且 VLAN ID 相同的包封時，則可按規則轉送。
	3.在table 0 加入規則，阻擋來自於主幹且來源 MAC address 為此的封包（預防 switch 間的迴圈問題）。
```
程式碼：

```python
@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
def _packet_in_handler(self, ev):
	...
	if not in_port in self.trunks[dpid]:
		# add self into the flow
		self.mac_to_port[dpid][src] = in_port
		table1_match = parser.OFPMatch(eth_src=src,vlan_vid=0x0000)
		table1_push_vlan_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,[parser.OFPActionPushVlan(ETH_TYPE_8021Q),parser.OFPActionSetField(vlan_vid=self.vlan_hosts[src])])
		table1_inst = [table1_push_vlan_action,parser.OFPInstructionGotoTable(table_id=2)]

		self._add_flow(datapath=datapath, match=table1_match,inst=table1_inst, priority=99,table=1)
			
		table2_match = parser.OFPMatch(eth_dst=src,vlan_vid=0x1000 | self.vlan_hosts[src])
		goto_the_port_actions = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,[parser.OFPActionPopVlan(ETH_TYPE_8021Q),parser.OFPActionOutput(in_port)])
		table2_inst = [goto_the_port_actions]

		for the_datapath_trunk in self.trunks[datapath.id]:
			table0_match = parser.OFPMatch(in_port=the_datapath_trunk,eth_src=src)
			drop_action = parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,[])
			table0_inst = [drop_action]
			self._add_flow(datapath=datapath, match=table0_match,inst= table0_inst, table=0)
		
		self._add_flow(datapath=datapath, match=table2_match, inst=table2_inst, priority=99, table=2)
	...
```

* 判定封包送出方式。邏輯如下：

```python
if 封包的目的主機在此 switch 中:
	代表 VLAN 不符合 -> drop
else:
	if 目的主機在其他 switch 中:
		直接由主幹傳出（如果傳入就是由主幹，則略過當初傳入的主幹）
	
	if 目的主機都不在目前的監控中:
		進行 Flooding，找尋目的主機
```

程式碼：

```python
@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
def _packet_in_handler(self, ev):
...
	if dst in self.mac_to_port[dpid]:
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
			out_port = ofproto.OFPP_FLOOD
			out_action = [parser.OFPActionPopVlan(ETH_TYPE_8021Q),parser.OFPActionOutput(out_port)]	
...
```

### Port 的狀況改變（有主機脫離）

預防主機脫離時，舊的規則影響整體運作。運作邏輯如下：

```python
if 狀態改變的 port 屬於某一個管理中的主機：
	清除 table 0 至 2 中，所有的相關規則
	清除 self.mac_to_port 中的記錄
```

程式碼：

```python
@set_ev_cls(ofp_event.EventOFPPortStateChange, MAIN_DISPATCHER)
def port_state_change_handler(self, ev):
...
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
...
```
# Version

* Beta
