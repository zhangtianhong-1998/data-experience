# Claim 消歧审计

- 投影 claim：53
- 规范化标签：23
- 不同实现签名：27
- 非通用同名歧义组：2
- 通用标签组：1
- 同实现跨标签候选：0

## 高风险标签

- `LONG_COL_0`：7 次观察，对应 3 种实现。
  - `['SUM']` ← `['dmgeorcdis.datain_1727073357645_temp.c2']`（Management_Analysis/w00819891/北京区域大屏）
  - `['SUM']` ← `['ads.ads_operation_daily.metric_value']`（经营汇总）
  - `['MAX']` ← `['dmregdis.datain_1757258241454_temp.c2']`（Management_Analysis/w00819891/ToB补录表250511）
- `日期`：4 次观察，对应 2 种实现。
  - `[]` ← `['dim.dim_calendar.calendar_date']`（公共/组织日历）
  - `[]` ← `['iot.dwd_device_status.stat_date']`（路径缺失）
- `月份`：2 次观察，对应 2 种实现。
  - `[]` ← `['dw.dwd_sales_order.month_key']`（Sales/w00123/订单利润数据集）
  - `[]` ← `['dw.dwd_receipt.month_key']`（Finance/回款事实集）

## 保守融合结论

- 标签不是实体 ID；系统别名尤其不能参与跨域自动融合。
- 相同实现只证明计算实现相近，不证明业务口径、过滤范围、单位或权限相同。
- 自动动作应止于局部 claim 去重；规范概念、同义词和企业指标需要更高等级证据或审批。
