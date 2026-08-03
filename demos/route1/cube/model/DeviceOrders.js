cube('DeviceOrders', {
  sql: 'SELECT * FROM device_orders',
  title: '设备订货事实',
  description: '合成数据。每行是一张设备订货单；指标只统计 confirmed 状态。',

  measures: {
    deviceOrderAmount: {
      sql: `CASE WHEN ${CUBE}.status = 'confirmed' THEN ${CUBE}.order_amount ELSE 0 END`,
      type: 'sum',
      title: '设备订货金额',
      description: '已确认设备订货单的 order_amount 合计，演示单位 CNY.'
    },
    deviceProfitAmount: {
      sql: `CASE WHEN ${CUBE}.status = 'confirmed' THEN ${CUBE}.profit_amount ELSE 0 END`,
      type: 'sum',
      title: '设备利润金额'
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
      type: 'string'
    },
    productL1: {
      sql: 'product_l1',
      type: 'string',
      title: '产品一级分类'
    },
    status: {
      sql: 'status',
      type: 'string'
    }
  }
});

