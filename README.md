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


# Version

* Beta