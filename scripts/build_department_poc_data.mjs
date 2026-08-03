#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve(
  process.argv[2] ??
    "outputs/019fb2dd-78a1-7871-8583-6a82e72af555/simulated_inputs",
);
const previewDir = path.join(outputDir, "previews");
await fs.mkdir(previewDir, { recursive: true });

const seed = 20260803;
let state = seed >>> 0;
function random() {
  state = (1664525 * state + 1013904223) >>> 0;
  return state / 2 ** 32;
}

function shuffled(items) {
  const result = [...items];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const target = Math.floor(random() * (index + 1));
    [result[index], result[target]] = [result[target], result[index]];
  }
  return result;
}

const reportPaths = {
  cockpit: "集团/销售经营部/u1001/【202608】销售经营驾驶舱",
  region: "销售经营部/区域销售月报",
  order: "集团/销售经营部/订单分析",
  customer: "SalesOps/u1002/客户经营分析",
  receipt: "集团//销售经营部/u1001/订单回款分析/",
  funnel: "SalesOps/商机漏斗看板",
  daily: "经营日报",
  finance: "集团/财务部/u2001/应收回款分析",
  device: "集团/制造中心/设备一部/u7788/传感器异常看板",
};

const sql = {
  grossSalesTrend: `SELECT o.month_key AS "月份",
       r.region_name AS "区域",
       SUM(o.sales_amount_gross) AS "销售额"
FROM dw.dwd_sales_order o
JOIN dw.dim_region r ON o.region_id = r.region_id
WHERE o.order_status = 'COMPLETED'
  AND o.month_key = ?
GROUP BY o.month_key, r.region_name
ORDER BY o.month_key`,
  grossSalesAlias: `SELECT r.region_name AS "区域",
       SUM(o.sales_amount_gross) AS "销额"
FROM dw.dwd_sales_order o
JOIN dw.dim_region r ON o.region_id = r.region_id
WHERE o.order_status = 'COMPLETED'
GROUP BY r.region_name`,
  netSalesSameLabel: `SELECT o.month_key AS "月份",
       SUM(o.sales_amount_net) AS "销售额"
FROM dw.dwd_sales_order o
WHERE o.order_status IN ('COMPLETED', 'RETURNED')
GROUP BY o.month_key`,
  orderDistinct: `SELECT p.product_type AS "产品类型",
       COUNT(DISTINCT o.order_id) AS "订单数",
       SUM(o.sales_amount_gross) AS "含税销售金额"
FROM dw.dwd_sales_order o
JOIN dw.dim_product p ON o.product_id = p.product_id
WHERE o.order_status = 'COMPLETED'
GROUP BY p.product_type`,
  orderRows: `SELECT o.month_key AS "月份",
       COUNT(*) AS "订单数"
FROM dw.dwd_sales_order o
WHERE o.order_status <> 'CANCELLED'
GROUP BY o.month_key`,
  receiptRate: `SELECT r.month_key AS "月份",
       SUM(r.receipt_amount) AS "回款金额",
       SUM(o.sales_amount_gross) AS "销售金额",
       SUM(r.receipt_amount) / NULLIF(SUM(o.sales_amount_gross), 0) AS "订单回款率"
FROM dw.dwd_receipt r
LEFT JOIN dw.dwd_sales_order o ON r.contract_id = o.contract_id
WHERE r.receipt_status = 'NORMAL'
  AND o.order_status = 'COMPLETED'
GROUP BY r.month_key`,
  financeReceiptRate: `SELECT r.month_key AS "月份",
       SUM(r.receipt_amount) / NULLIF(SUM(a.receivable_amount), 0) AS "回款率"
FROM dw.dwd_receipt r
JOIN fin.dwd_receivable a ON r.contract_id = a.contract_id
WHERE r.receipt_status IN ('NORMAL', 'OFFSET')
GROUP BY r.month_key`,
  customerLevel: `SELECT c.customer_level AS "客户等级",
       COUNT(DISTINCT c.customer_id) AS "客户数",
       SUM(o.sales_amount_gross) AS "销售额"
FROM dw.dim_customer c
LEFT JOIN dw.dwd_sales_order o ON c.customer_id = o.customer_id
WHERE c.customer_status = 'ACTIVE'
GROUP BY c.customer_level`,
  opaqueDaily: `SELECT t.c2 AS "年月",
       t.c5 AS "区域",
       SUM(t.c7) AS "LONG_COL_0"
FROM ads.datain_sales_daily_temp t
WHERE t.c0 = ?
GROUP BY t.c2, t.c5`,
  calendarFilter: `SELECT c.calendar_date AS "日期",
       c.month_name AS "月份名称"
FROM dim.dim_calendar c
WHERE c.calendar_date BETWEEN ? AND ?`,
  opportunity: `SELECT o.stage_name AS "商机阶段",
       COUNT(DISTINCT o.opportunity_id) AS "商机数",
       SUM(o.expected_amount) AS "预计金额"
FROM crm.dwd_opportunity o
WHERE o.is_deleted = 0
GROUP BY o.stage_name`,
  alarm: `SELECT s.stat_date AS "日期",
       d.device_type AS "设备类型",
       COUNT(s.alarm_code) AS "告警次数"
FROM iot.dwd_device_status s
JOIN iot.dim_device d ON s.device_id = d.device_id
WHERE s.org_id = ?
GROUP BY s.stat_date, d.device_type`,
  temperature: `SELECT t.collect_time AS "采集时间",
       t.sensor_code AS "传感器编号",
       AVG(t.temperature) AS "平均温度"
FROM iot.dwd_sensor_temperature t
WHERE t.device_id = ?
GROUP BY t.collect_time, t.sensor_code`,
};

const baseExecutionRows = [
  [reportPaths.cockpit, "销售金额趋势", "Sales/u1001/订单利润主题", sql.grossSalesTrend],
  [reportPaths.cockpit, "图表4", "Sales/u1001/订单利润主题", sql.orderDistinct],
  [reportPaths.cockpit, "订单回款率", "Sales/u1001/回款协同主题", sql.receiptRate],
  [reportPaths.cockpit, "日期筛选", "公共/组织日历", sql.calendarFilter],
  [reportPaths.region, "区域销额", "Sales/区域经营宽表", sql.grossSalesAlias],
  [reportPaths.region, "销售额趋势", "Sales/区域经营宽表", sql.netSalesSameLabel],
  [reportPaths.region, "筛选器2", "公共/组织日历", sql.calendarFilter],
  [reportPaths.order, "订单量趋势", "Sales/订单明细主题", sql.orderDistinct],
  [reportPaths.order, "订单量趋势", "Sales/订单明细主题", sql.orderRows],
  [reportPaths.customer, "客户等级贡献", "Sales/客户贡献主题", sql.customerLevel],
  [reportPaths.customer, "组件12", null, sql.customerLevel],
  [reportPaths.receipt, "订单回款率", "Sales/u1001/订单利润主题", sql.grossSalesTrend],
  [reportPaths.receipt, "订单回款率", "Sales/u1001/回款协同主题", sql.receiptRate],
  [reportPaths.receipt, "回款明细", "Sales/u1001/回款协同主题", null],
  [reportPaths.funnel, "商机阶段转化", "CRM/销售商机主题", sql.opportunity],
  [reportPaths.daily, null, "经营汇总", sql.opaqueDaily],
  [reportPaths.finance, "回款率", "Finance/应收回款主题", sql.financeReceiptRate],
  [reportPaths.finance, "回款金额按客户等级", "Finance/应收回款主题", sql.customerLevel],
  [reportPaths.device, "设备告警趋势", "Operations/设备状态宽表", sql.alarm],
  [reportPaths.device, "图表9", "Operations/温度传感器明细", sql.temperature],
];

const executionRows = shuffled([
  ...baseExecutionRows,
  // 确定性随机噪声：重复执行、路径空白/双斜杠、非法 SQL、空报表路径。
  baseExecutionRows[Math.floor(random() * 4)],
  [
    " 集团 // 销售经营部 / u1001 /【202608】销售经营驾驶舱/ ",
    " 销售金额趋势 ",
    "Sales//u1001/订单利润主题/",
    sql.grossSalesTrend,
  ],
  [reportPaths.order, "图表99", "Sales/订单明细主题", "SELEC bad syntax FROM"],
  [null, "孤立组件", "不存在/孤立数据集", "SELECT x FROM unknown_table"],
]);

const lineageRows = shuffled([
  [reportPaths.cockpit, "Sales/u1001/订单利润主题", "销售额", "dw.dwd_sales_order", "sales_amount_gross"],
  [reportPaths.cockpit, "Sales/u1001/订单利润主题", "订单编号", "dw.dwd_sales_order", "order_id"],
  [reportPaths.cockpit, "Sales/u1001/回款协同主题", "订单回款率", "dw.dwd_receipt", "receipt_amount"],
  [reportPaths.region, "Sales/区域经营宽表", "销额", "dw.dwd_sales_order", "sales_amount_gross"],
  [reportPaths.region, "Sales/区域经营宽表", "销售额", "dw.dwd_sales_order", "sales_amount_net"],
  [reportPaths.order, "Sales/订单明细主题", "订单数", "dw.dwd_sales_order", "order_id"],
  [reportPaths.customer, "Sales/客户贡献主题", "客户编号", "dw.dim_customer", "customer_id"],
  [reportPaths.customer, "Sales/客户贡献主题", "客商编码", "dw.dwd_sales_order", "customer_id"],
  [reportPaths.receipt, "Sales/u1001/回款协同主题", "回款金额", "dw.dwd_receipt", "receipt_amount"],
  [reportPaths.funnel, "CRM/销售商机主题", "商机", "crm.dwd_opportunity", "opportunity_id"],
  [reportPaths.daily, "经营汇总", "销售金额", "ads.datain_sales_daily_temp", "c7"],
  [reportPaths.finance, "Finance/应收回款主题", "回款率", "fin.dwd_receivable", "receivable_amount"],
  [reportPaths.device, "Operations/设备状态宽表", "温度", "iot.dwd_device_status", "temperature"],
  [reportPaths.device, "Operations/温度传感器明细", "原始报文", "iot.dwd_sensor_temperature", "raw_payload"],
  // 噪声：错字字段、孤立血缘、缺失字段。
  [reportPaths.cockpit, "Sales/u1001/订单利润主题", "销售金额_疑似错字", "dw.dwd_sales_order", "sales_amunt"],
  ["不存在/孤立看板", "不存在/孤立数据集", "孤立字段", "unknown_table", null],
]);

const tableMetadata = {
  "dw.dwd_sales_order": {
    cn_name: "销售订单事实表",
    fields: [
      { field: "order_id", comment: "订单编号；同一订单只有一个编号" },
      { field: "contract_id", comment: "合同编号" },
      { field: "customer_id", comment: "客户ID" },
      { field: "order_status", comment: "订单状态：DRAFT、COMPLETED、CANCELLED、RETURNED" },
      { field: "order_date", comment: "订单业务日期" },
      { field: "month_key", comment: "业务年月，格式YYYYMM" },
      { field: "region_id", comment: "销售区域编号" },
      { field: "product_id", comment: "产品编号" },
      { field: "sales_amount_gross", comment: "含税销售金额，单位：元" },
      { field: "sales_amount_net", comment: "不含税销售金额，单位：元；退货订单可能为负" },
      { field: "org_id", comment: "销售组织编号" },
    ],
  },
  "dw.dwd_receipt": {
    cn_name: "合同回款事实表",
    fields: [
      { field: "contract_id", comment: "合同编号" },
      { field: "customer_id", comment: "客商编码，与客户ID为同一业务键" },
      { field: "month_key", comment: "回款月份" },
      { field: "receipt_amount", comment: "实际回款金额，单位：元" },
      { field: "receipt_status", comment: "回款状态：NORMAL、FROZEN、OFFSET" },
    ],
  },
  "dw.dim_customer": {
    cn_name: "客户维表",
    fields: [
      { field: "customer_id", comment: "客户编号" },
      { field: "customer_name", comment: "客户名称" },
      { field: "customer_level", comment: "客户等级：战略、重点、普通" },
      { field: "customer_status", comment: "客户状态：ACTIVE、FROZEN、CLOSED" },
    ],
  },
  "dw.dim_region": {
    cn_name: "销售区域维表",
    fields: [
      { field: "region_id", comment: "区域编号" },
      { field: "region_name", comment: "区域名称" },
    ],
  },
  "dw.dim_product": {
    cn_name: "产品维表",
    fields: [
      { field: "product_id", comment: "产品编号" },
      { field: "product_type", comment: "产品类型" },
      { field: "product_line", comment: "产品线" },
    ],
  },
  "fin.dwd_receivable": {
    cn_name: "应收事实表",
    fields: [
      { field: "contract_id", comment: "合同编号" },
      { field: "receivable_amount", comment: "确认应收金额，单位：元" },
    ],
  },
  "ads.datain_sales_daily_temp": {
    cn_name: "经营日报临时宽表",
    fields: [
      { field: "c0", comment: "组织编号" },
      { field: "c2", comment: "年月" },
      { field: "c5", comment: "销售区域" },
      { field: "c7", comment: "已完成订单含税销售额，单位：元" },
    ],
  },
  "crm.dwd_opportunity": {
    cn_name: "销售商机事实表",
    fields: [
      { field: "opportunity_id", comment: "商机编号" },
      { field: "stage_name", comment: "商机阶段：线索、验证、方案、赢单、输单" },
      { field: "expected_amount", comment: "预计成交金额，单位：元" },
      { field: "is_deleted", comment: "逻辑删除标记，0有效，1删除" },
    ],
  },
  "dim.dim_calendar": {
    cn_name: "公共日历维表",
    fields: [
      { field: "calendar_date", comment: "自然日期" },
      { field: "month_name", comment: "月份名称" },
    ],
  },
  "iot.dwd_device_status": {
    cn_name: "设备状态事实表",
    fields: [
      { field: "stat_date", comment: "统计日期" },
      { field: "device_id", comment: "设备编号" },
      { field: "alarm_code", comment: "告警编码" },
      { field: "temperature", comment: "设备温度，单位：摄氏度" },
      { field: "org_id", comment: "组织编号" },
    ],
  },
  "iot.dim_device": {
    cn_name: "设备维表",
    fields: [
      { field: "device_id", comment: "设备编号" },
      { field: "device_type", comment: "设备类型" },
    ],
  },
  "iot.dwd_sensor_temperature": {
    cn_name: "温度传感器明细表",
    fields: [
      { field: "collect_time", comment: "采集时间" },
      { field: "sensor_code", comment: "传感器编号" },
      { field: "device_id", comment: "设备编号" },
      { field: "temperature", comment: "温度，单位：摄氏度" },
      { field: "raw_payload", comment: null },
    ],
  },
  "legacy.unused_table": {
    cn_name: null,
    fields: [],
  },
};

const reportMapping = {
  "【202608】销售经营驾驶舱": {
    cn_name: "销售经营驾驶舱",
    table_id: "bi_report_sales_001",
    target_dataset_id: "sales_order_profit_v3",
  },
  "区域销售月报": {
    cn_name: "区域销售月报",
    table_id: "bi_report_sales_002",
    target_dataset_id: "regional_sales_ops",
  },
  "订单分析": {
    cn_name: "销售订单分析",
    table_id: "bi_report_sales_003",
    target_dataset_id: "sales_order_detail",
  },
  "客户经营分析": {
    cn_name: "客户经营与贡献分析",
    table_id: "bi_report_sales_004",
    target_dataset_id: "customer_contribution",
  },
  "订单回款分析": {
    cn_name: "订单回款协同分析",
    table_id: "bi_report_sales_005",
    target_dataset_id: "order_receipt_subject",
  },
  "商机漏斗看板": {
    cn_name: "销售商机漏斗看板",
    table_id: "bi_report_sales_006",
    target_dataset_id: "crm_opportunity_funnel",
  },
  "经营日报": {
    cn_name: "销售经营日报",
    table_id: "bi_report_sales_007",
    target_dataset_id: "sales_daily_opaque",
  },
  "应收回款分析": {
    cn_name: "财务应收与回款分析",
    table_id: "bi_report_fin_001",
    target_dataset_id: "finance_receivable_receipt",
  },
  "传感器异常看板": {
    cn_name: "设备传感器异常看板",
    table_id: "bi_report_iot_001",
    target_dataset_id: "iot_sensor_monitoring",
  },
  "已下线报表": {
    cn_name: "历史下线报表",
    table_id: null,
    target_dataset_id: null,
  },
};

const experimentScope = {
  schema_version: "experiment-scope-v1",
  group: { ref: "group://demo", name: "演示集团" },
  selected_department_ref: "department://sales-operations",
  departments: [
    {
      department_ref: "department://sales-operations",
      name: "销售经营部",
      assignment_method: "configured_for_experiment",
      report_paths: [
        reportPaths.cockpit,
        reportPaths.region,
        reportPaths.order,
        reportPaths.customer,
        reportPaths.receipt,
        reportPaths.funnel,
        reportPaths.daily,
      ],
    },
    {
      department_ref: "department://finance",
      name: "财务部",
      assignment_method: "configured_for_experiment",
      report_paths: [reportPaths.finance],
    },
    {
      department_ref: "department://manufacturing-device",
      name: "制造中心设备一部",
      assignment_method: "configured_for_experiment",
      report_paths: [reportPaths.device],
    },
  ],
  policy: {
    cross_department_alignment: false,
    allow_path_inferred_department_as_fact: false,
    max_alignment_candidates_per_mention: 5,
  },
};

const simulationTruth = {
  schema_version: "simulation-truth-v1",
  note: "仅用于程序评测，不得进入语义抽取证据包。",
  expected_local_semantics: [
    {
      report_path: reportPaths.cockpit,
      concepts: ["销售额", "订单数", "订单回款率", "月份", "区域", "产品类型"],
    },
    {
      report_path: reportPaths.region,
      concepts: ["销额", "销售额", "月份", "区域"],
      conflict: "同一报表中的销售额包含含税已完成口径和不含税含退货口径",
    },
    {
      report_path: reportPaths.order,
      concepts: ["订单数", "产品类型", "月份"],
      conflict: "COUNT(DISTINCT order_id) 与 COUNT(*) 不是同一实现",
    },
  ],
  expected_department_alignments: [
    { left: "销售额", right: "销额", decision: "equivalent_or_alias_when_qualifiers_match" },
    { left: "含税销售额", right: "不含税销售额", decision: "variant_or_conflict_not_merge" },
    { left: "订单数_distinct", right: "订单数_rows", decision: "conflict_not_merge" },
    { left: "销售订单回款率", right: "财务回款率", decision: "outside_department_first_round" },
  ],
};

const goldQuestions = [
  {
    question_id: "Q001",
    question: "查询销售经营部按月和区域统计的已完成订单含税销售额。",
    task_type: "asset_and_metric_selection",
    expected: {
      tables: ["dw.dwd_sales_order", "dw.dim_region"],
      fields: ["month_key", "region_name", "sales_amount_gross", "order_status"],
      aggregation: "SUM",
      filters: ["order_status = COMPLETED"],
      report_titles: ["销售经营驾驶舱", "区域销售月报"],
    },
  },
  {
    question_id: "Q002",
    question: "区域销售月报里的销售额和销额是不是完全同一个口径？",
    task_type: "conflict_explanation",
    expected: {
      decision: "not_equivalent",
      required_fields: ["sales_amount_gross", "sales_amount_net", "order_status"],
      required_terms: ["含税", "不含税", "退货", "已完成"],
    },
  },
  {
    question_id: "Q003",
    question: "订单分析里的订单数有几种算法，能直接合并吗？",
    task_type: "conflict_explanation",
    expected: {
      decision: "not_equivalent",
      required_expressions: ["COUNT(DISTINCT order_id)", "COUNT(*)"],
    },
  },
  {
    question_id: "Q004",
    question: "客户编号、客户ID和客商编码在当前销售经营部样例中分别落到哪些字段？",
    task_type: "alias_schema_linking",
    expected: {
      tables: ["dw.dim_customer", "dw.dwd_sales_order", "dw.dwd_receipt"],
      field: "customer_id",
    },
  },
  {
    question_id: "Q005",
    question: "销售经营驾驶舱中的订单回款率是怎么计算的？",
    task_type: "metric_definition",
    expected: {
      numerator: "SUM(dw.dwd_receipt.receipt_amount)",
      denominator: "SUM(dw.dwd_sales_order.sales_amount_gross)",
      filters: ["receipt_status = NORMAL", "order_status = COMPLETED"],
    },
  },
  {
    question_id: "Q006",
    question: "财务部回款率是否应该在本轮自动并入销售经营部订单回款率？",
    task_type: "scope_guard",
    expected: {
      decision: "no",
      reason: "cross_department_disabled_and_denominator_differs",
    },
  },
];

const warehouseRows = {
  note: "仅用于未来 SQL 执行评测；不进入抽取上下文。",
  tables: {
    "dw.dwd_sales_order": [
      { order_id: "O1", contract_id: "C1", customer_id: "U1", order_status: "COMPLETED", month_key: "202608", region_id: "R1", product_id: "P1", sales_amount_gross: 1130, sales_amount_net: 1000 },
      { order_id: "O2", contract_id: "C2", customer_id: "U2", order_status: "RETURNED", month_key: "202608", region_id: "R1", product_id: "P2", sales_amount_gross: -565, sales_amount_net: -500 },
      { order_id: "O3", contract_id: "C3", customer_id: "U1", order_status: "COMPLETED", month_key: "202608", region_id: "R2", product_id: "P1", sales_amount_gross: 2260, sales_amount_net: 2000 },
    ],
    "dw.dwd_receipt": [
      { contract_id: "C1", customer_id: "U1", month_key: "202608", receipt_amount: 565, receipt_status: "NORMAL" },
      { contract_id: "C3", customer_id: "U1", month_key: "202608", receipt_amount: 1130, receipt_status: "NORMAL" },
    ],
    "dw.dim_region": [
      { region_id: "R1", region_name: "华东" },
      { region_id: "R2", region_name: "华北" },
    ],
  },
};

function applyRawStyle(sheet, usedRange, widths) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const header = usedRange.getRow(0);
  header.format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  header.format.rowHeightPx = 30;
  usedRange.format.font = { name: "Aptos", size: 10 };
  usedRange.format.verticalAlignment = "top";
  usedRange.format.wrapText = true;
  widths.forEach((width, index) => {
    usedRange.getColumn(index).format.columnWidthPx = width;
  });
  usedRange.format.borders = {
    insideHorizontal: { style: "thin", color: "#D9E2F3" },
    bottom: { style: "thin", color: "#9FBAD0" },
  };
}

async function buildWorkbook({ name, sheetName, headers, rows, widths }) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(sheetName);
  const matrix = [headers, ...rows];
  const range = sheet.getRangeByIndexes(0, 0, matrix.length, headers.length);
  range.values = matrix;
  applyRawStyle(sheet, range, widths);
  const table = sheet.tables.add(range, true, `${sheetName.replace(/[^A-Za-z0-9]/g, "")}Table`);
  table.style = "TableStyleMedium2";
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, name.replace(/\.xlsx$/i, ".png")),
    new Uint8Array(await preview.arrayBuffer()),
  );
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(outputDir, name));

  const inspection = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!A1:${String.fromCharCode(64 + headers.length)}${matrix.length}`,
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: headers.length,
  });
  return {
    name,
    sheet_name: sheetName,
    row_count: rows.length,
    inspection: inspection.ndjson,
  };
}

const workbookResults = [];
workbookResults.push(
  await buildWorkbook({
    name: "BI_SQL执行明细_部门实验.xlsx",
    sheetName: "SQL执行明细",
    headers: ["报表路径", "组件名称", "数据集路径", "执行SQL"],
    rows: executionRows,
    widths: [310, 180, 300, 620],
  }),
);
workbookResults.push(
  await buildWorkbook({
    name: "报表字段血缘_部门实验.xlsx",
    sheetName: "字段血缘",
    headers: ["报表路径", "依赖的数据集路径", "绑定的列名", "依赖的物理表名", "依赖的数据库字段"],
    rows: lineageRows,
    widths: [310, 300, 180, 260, 220],
  }),
);

const jsonOutputs = {
  "数据字段信息.json": tableMetadata,
  "报表使用的数据映射.json": reportMapping,
  "实验范围.json": experimentScope,
  "模拟数据真值_禁止作为抽取输入.json": simulationTruth,
  "评测问题与标准答案.json": goldQuestions,
  "评测行数据_禁止作为抽取输入.json": warehouseRows,
};
for (const [name, value] of Object.entries(jsonOutputs)) {
  await fs.writeFile(
    path.join(outputDir, name),
    `${JSON.stringify(value, null, 2)}\n`,
    "utf8",
  );
}

const manifest = {
  schema_version: "simulated-input-manifest-v1",
  seed,
  generated_at: new Date().toISOString(),
  output_dir: outputDir,
  selected_department: "销售经营部",
  source_files: [
    "BI_SQL执行明细_部门实验.xlsx",
    "报表字段血缘_部门实验.xlsx",
    "数据字段信息.json",
    "报表使用的数据映射.json",
  ],
  configuration_files: ["实验范围.json"],
  evaluation_only_files: [
    "模拟数据真值_禁止作为抽取输入.json",
    "评测问题与标准答案.json",
    "评测行数据_禁止作为抽取输入.json",
  ],
  counts: {
    execution_rows: executionRows.length,
    lineage_rows: lineageRows.length,
    physical_tables: Object.keys(tableMetadata).length,
    report_mappings: Object.keys(reportMapping).length,
  },
  noise: [
    "1至5段及空段路径",
    "空组件名、系统组件名、空数据集路径和空SQL",
    "重复执行与同组件多SQL",
    "同组件名称跨数据集",
    "一个SQL多物理表",
    "无语义别名与不透明字段",
    "同义词、同名不同口径、单位与过滤差异",
    "错误字段血缘、孤立血缘、未登记物理表和非法SQL",
    "公共维表及部门外传感器资产",
  ],
  workbooks: workbookResults.map(({ inspection, ...item }) => item),
};
await fs.writeFile(
  path.join(outputDir, "模拟数据清单.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

for (const result of workbookResults) {
  process.stdout.write(`${JSON.stringify(result)}\n`);
}
process.stdout.write(`${JSON.stringify(manifest, null, 2)}\n`);
