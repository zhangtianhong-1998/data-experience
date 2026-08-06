cube('DeviceOrders', {
  sql: 'SELECT * FROM device_orders',
  title: '设备订货事实',
  description: '合成数据。每行是一张设备订货单；指标只统计 confirmed 状态。本模型用于设备订货，不用于销售金额。',

  measures: {
    deviceOrderAmount: {
      sql: `CASE WHEN ${CUBE}.status = 'confirmed' THEN ${CUBE}.order_amount ELSE 0 END`,
      type: 'sum',
      title: '设备订货金额',
      description: '已确认设备订货单的 order_amount 合计，演示单位 CNY.',
      meta: {
        ai_context: '同义词包括“设备订货额”和“设备订单金额”。不能用于“销售金额”。用户只说“金额”时，无法区分订货金额和利润金额，必须追问。'
      }
    },
    deviceProfitAmount: {
      sql: `CASE WHEN ${CUBE}.status = 'confirmed' THEN ${CUBE}.profit_amount ELSE 0 END`,
      type: 'sum',
      title: '设备利润金额',
      description: '已确认设备订货单的设备利润合计；不能解释为净利润。',
      meta: {
        ai_context: '同义词包括“设备利润额”。用户明确询问净利润时不得使用本指标。用户只说“金额”时，无法区分订货金额和利润金额，必须追问。'
      }
    },
    orderCount: {
      type: 'count',
      filters: [{ sql: `${CUBE}.status = 'confirmed'` }]
    }
  },

  dimensions: {
    orderId: {
      sql: 'order_id',
      type: 'string',
      primaryKey: true
    },
    orderDate: {
      sql: 'order_date',
      type: 'time'
    },
    yearMonth: {
      sql: 'year_month',
      type: 'number'
    },
    orgCode: {
      sql: 'org_code',
      type: 'string',
      description: '组织编码；每次设备经营分析必须由用户显式给出。',
      meta: {
        ai_context: '必填过滤维度；不得默认跨组织汇总，也不得猜测组织编码。'
      }
    },
    productL1: {
      sql: 'product_l1',
      type: 'string',
      title: '产品一级分类',
      meta: {
        ai_context: '“产品大类”在本模型中指产品一级分类。'
      }
    },
    status: {
      sql: 'status',
      type: 'string'
    }
  }
});
