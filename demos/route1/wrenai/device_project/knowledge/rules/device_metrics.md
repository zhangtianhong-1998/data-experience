# 设备业务规则

- `device_order_amount` 只合计 `status = 'confirmed'` 的 `order_amount`。
- 查询必须显式给出 `org_code`，不得默认跨组织汇总。
- 演示金额单位为 CNY。
- “设备订货额”“设备订单金额”都指 `device_order_amount`；“设备利润额”指 `device_profit_amount`。
- 用户只说“金额”时，无法区分订货金额和利润金额，必须追问。
- `device_profit_amount` 是设备利润，不是净利润；用户明确询问净利润时不得替代。
- “销售金额”属于 `sales_orders`，不能代替设备订货金额。
