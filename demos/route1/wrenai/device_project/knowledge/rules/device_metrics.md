# 设备业务规则

- `device_order_amount` 只合计 `status = 'confirmed'` 的 `order_amount`。
- 查询必须显式给出 `org_code`，不得默认跨组织汇总。
- 演示金额单位为 CNY。
- “销售金额”属于 `sales_orders`，不能代替设备订货金额。

