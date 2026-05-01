const express = require('express');
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(express.json());

const DATA_FILE = path.join(__dirname, 'data', 'billing.json');
const ORDERS_POLL_FILE = path.join(__dirname, 'data', 'pending_transfers.json');
const TX_FILE = path.join(__dirname, 'data', 'transactions.json');

const CONFIG = {
  port: 4313,
  trc20Address: 'TKYp9dbDs6kHKtFhFR6srEJvDARNYkq9Qe',
  rechargeRate: 100,
  imageCost: 50,
  newUserBonus: 100,
  referralBonus: 300,
  referralMinRecharge: 10,
  pollInterval: 10000,
  orderTimeout: 15 * 60 * 1000,
  admins: ['825512163', '8277934317'],
  trongridApi: 'https://api.trongrid.io',
  telegramBotToken: process.env.TELEGRAM_BOT_TOKEN || '',
  tronPollInterval: 15000,
  lastCheckedTxTimestamp: Date.now(),
};

function loadData() {
  try { return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8')); }
  catch { return { users: {}, orders: {} }; }
}

function saveData(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
}

function loadPending() {
  try { return JSON.parse(fs.readFileSync(ORDERS_POLL_FILE, 'utf8')); }
  catch { return []; }
}

function savePending(pending) {
  fs.writeFileSync(ORDERS_POLL_FILE, JSON.stringify(pending, null, 2));
}

function loadTx() {
  try { return JSON.parse(fs.readFileSync(TX_FILE, 'utf8')); }
  catch { return []; }
}

function saveTx(tx) {
  fs.writeFileSync(TX_FILE, JSON.stringify(tx, null, 2));
}

function addTx(userId, type, amount, reason, extra = {}) {
  const tx = loadTx();
  tx.unshift({
    id: `TX_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    userId, type, amount, reason,
    createdAt: Date.now(),
    ...extra
  });
  saveTx(tx);
  return tx[0];
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;
    client.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { reject(new Error('Invalid JSON')); }
      });
    }).on('error', reject);
  });
}

function notifyTelegram(chatId, message) {
  if (!CONFIG.telegramBotToken || !chatId) return Promise.resolve();
  return new Promise((resolve) => {
    const url = `https://api.telegram.org/bot${CONFIG.telegramBotToken}/sendMessage?chat_id=${chatId}&text=${encodeURIComponent(message)}&parse_mode=Markdown`;
    https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', resolve);
    }).on('error', resolve);
  });
}

function getOrCreateUser(userId) {
  const data = loadData();
  if (!data.users[userId]) {
    data.users[userId] = {
      id: userId, balance: 0, bonusClaimed: false, createdAt: Date.now(),
      referrerId: null, referralEarnings: 0, pendingReferralCredits: 0
    };
    saveData(data);
  }
  return data.users[userId];
}

app.get('/health', (req, res) => res.json({ status: 'ok', timestamp: Date.now() }));

app.get('/user/:userId', (req, res) => res.json(getOrCreateUser(req.params.userId)));

app.get('/balance/:userId', (req, res) => {
  const user = getOrCreateUser(req.params.userId);
  res.json({ userId: user.id, balance: user.balance });
});

app.post('/deduct', (req, res) => {
  const { userId, amount, reason } = req.body;
  if (!userId || amount === undefined)
    return res.status(400).json({ error: 'userId and amount required' });

  const user = getOrCreateUser(userId);
  if (user.balance < amount)
    return res.status(400).json({ error: 'Insufficient balance', balance: user.balance });

  user.balance -= amount;
  const data = loadData();
  data.users[userId] = user;
  saveData(data);

  addTx(userId, 'deduct', amount, reason || 'image_generation');

  res.json({ success: true, balance: user.balance, deducted: amount, reason });
});

app.post('/recharge', (req, res) => {
  const { userId, amount, coin } = req.body;
  if (!userId || !amount || !coin)
    return res.status(400).json({ error: 'userId, amount, coin required' });

  const orderId = `ORDER_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const baseAmount = Math.floor(amount);
  const randomCents = Math.floor(Math.random() * 99) + 1;
  const displayAmount = baseAmount + (randomCents / 100);
  const credits = Math.floor(baseAmount * CONFIG.rechargeRate);
  const data = loadData();
  const pending = loadPending();

  data.orders[orderId] = {
    id: orderId, userId, baseAmount, displayAmount, coin, credits,
    status: 'pending',
    createdAt: Date.now(),
    expiresAt: Date.now() + CONFIG.orderTimeout,
    txHash: null
  };
  saveData(data);

  addTx(userId, 'recharge', credits, 'USDT deposit', { orderId, displayAmount, coin });

  pending.push({
    orderId, userId, displayAmount, baseAmount, coin, credits,
    status: 'pending',
    expiresAt: Date.now() + CONFIG.orderTimeout,
    notified: false
  });
  savePending(pending);

  res.json({
    orderId, userId, amount: displayAmount, baseAmount, coin,
    address: CONFIG.trc20Address,
    credits,
    expiresAt: new Date(Date.now() + CONFIG.orderTimeout).toISOString(),
    status: 'pending'
  });
});

app.get('/order/:orderId', (req, res) => {
  const data = loadData();
  const order = data.orders[req.params.orderId];
  if (!order) return res.status(404).json({ error: 'Order not found' });
  res.json(order);
});

app.get('/orders/:userId', (req, res) => {
  const data = loadData();
  const orders = Object.values(data.orders)
    .filter(o => o.userId === req.params.userId)
    .sort((a, b) => b.createdAt - a.createdAt)
    .slice(0, 50);
  res.json(orders);
});

app.post('/refund', (req, res) => {
  const { userId, amount, reason } = req.body;
  if (!userId || !amount) return res.status(400).json({ error: 'userId and amount required' });

  const user = getOrCreateUser(userId);
  user.balance += amount;
  const data = loadData();
  data.users[userId] = user;
  saveData(data);

  addTx(userId, 'refund', amount, reason || 'refund');

  res.json({ success: true, balance: user.balance, refunded: amount, reason });
});

app.post('/claim-bonus', (req, res) => {
  const { userId } = req.body;
  if (!userId) return res.status(400).json({ error: 'userId required' });

  const user = getOrCreateUser(userId);
  if (user.bonusClaimed) return res.status(400).json({ error: 'Bonus already claimed', claimed: true });

  user.balance += CONFIG.newUserBonus;
  user.bonusClaimed = true;
  const data = loadData();
  data.users[userId] = user;
  saveData(data);

  addTx(userId, 'bonus', CONFIG.newUserBonus, 'new user bonus');

  res.json({ success: true, bonus: CONFIG.newUserBonus, newBalance: user.balance });
});

app.post('/add-balance', (req, res) => {
  const { userId, amount } = req.body;
  if (!userId || !amount) return res.status(400).json({ error: 'userId and amount required' });

  const data = loadData();
  if (!data.users[userId]) return res.status(404).json({ error: 'User not found' });

  data.users[userId].balance += amount;
  saveData(data);

  res.json({ success: true, userId, added: amount, newBalance: data.users[userId].balance });
});

app.post('/admin/add-balance', (req, res) => {
  const { userId, amount } = req.body;
  if (!userId || !amount) return res.status(400).json({ error: 'userId and amount required' });

  const user = getOrCreateUser(userId);
  user.balance += amount;
  const data = loadData();
  data.users[userId] = user;
  saveData(data);

  res.json({ success: true, userId, added: amount, newBalance: user.balance });
});

app.get('/admin/users', (req, res) => {
  const data = loadData();
  const users = Object.values(data.users)
    .map(u => ({ id: u.id, balance: u.balance, bonusClaimed: u.bonusClaimed, createdAt: u.createdAt }))
    .sort((a, b) => b.createdAt - a.createdAt);
  res.json(users);
});

app.post('/notify-transfer', (req, res) => {
  const { orderId, txHash } = req.body;
  if (!orderId || !txHash) return res.status(400).json({ error: 'orderId and txHash required' });

  const data = loadData();
  const order = data.orders[orderId];
  if (!order) return res.status(404).json({ error: 'Order not found' });
  if (order.status !== 'pending') return res.status(400).json({ error: 'Order not pending', status: order.status });

  order.txHash = txHash;
  order.status = 'completed';
  order.completedAt = Date.now();

  const user = getOrCreateUser(order.userId);
  user.balance += order.credits;

  // 推荐人返现：被推荐人充值 >= 10 USDT，推荐人得 300 积分
  let referralBonus = 0;
  if (user.referrerId && order.baseAmount >= CONFIG.referralMinRecharge) {
    const referrer = data.users[user.referrerId];
    if (referrer) {
      referrer.balance += CONFIG.referralBonus;
      referrer.referralEarnings = (referrer.referralEarnings || 0) + CONFIG.referralBonus;
      referralBonus = CONFIG.referralBonus;
      addTx(user.referrerId, 'referral_bonus', CONFIG.referralBonus, `推荐返现: ${order.userId} 充值 ${order.baseAmount} USDT`);
    }
  }

  data.users[order.userId] = user;
  data.orders[orderId] = order;
  saveData(data);

  addTx(order.userId, 'recharge_complete', order.credits, 'USDT deposit confirmed', { orderId, txHash });

  res.json({ success: true, orderId, credits: order.credits, newBalance: user.balance, referralBonus });
});

app.get('/pending-orders', (req, res) => {
  const pending = loadPending().filter(p => p.expiresAt > Date.now());
  savePending(pending);
  res.json(pending);
});

app.post('/bind-referrer', (req, res) => {
  const { userId, referrerId } = req.body;
  if (!userId || !referrerId) return res.status(400).json({ error: 'userId and referrerId required' });
  if (userId === referrerId) return res.status(400).json({ error: 'Cannot refer yourself' });

  const data = loadData();
  const user = getOrCreateUser(userId);

  // 已经绑定过推荐人，不再重复绑定
  if (user.referrerId) return res.json({ success: true, alreadyBound: true, referrerId: user.referrerId });

  // 推荐人必须存在
  if (!data.users[referrerId]) return res.status(404).json({ error: 'Referrer not found' });

  user.referrerId = referrerId;
  data.users[userId] = user;
  saveData(data);

  res.json({ success: true, referrerId });
});

app.get('/referral/:userId', (req, res) => {
  const data = loadData();
  const user = getOrCreateUser(req.params.userId);

  const referrals = Object.values(data.users).filter(u => u.referrerId === req.params.userId);

  res.json({
    referralCount: referrals.length,
    totalEarnings: user.referralEarnings || 0,
    pendingCredits: user.pendingReferralCredits || 0,
  });
});

app.get('/transactions/:userId', (req, res) => {
  const tx = loadTx().filter(t => t.userId === req.params.userId).slice(0, 50);
  res.json(tx);
});

function checkPendingOrders() {
  const pending = loadPending();
  const now = Date.now();
  const data = loadData();
  let changed = false;

  const remaining = pending.filter(p => {
    if (now > p.expiresAt) {
      if (data.orders[p.orderId] && data.orders[p.orderId].status === 'pending') {
        data.orders[p.orderId].status = 'expired';
        changed = true;
      }
      return false;
    }
    return true;
  });

  if (changed) saveData(data);
  if (JSON.stringify(pending) !== JSON.stringify(remaining)) savePending(remaining);
}

async function checkTronTransfers() {
  try {
    const url = `${CONFIG.trongridApi}/v1/accounts/${CONFIG.trc20Address}/transactions/trc20?only_confirmed=true&limit=50`;
    const result = await httpGet(url);

    if (!result.data || !Array.isArray(result.data)) return;

    const pending = loadPending();
    const activePending = pending.filter(p => p.status === 'pending');
    
    if (activePending.length === 0) {
      console.log('[TRON检查] 无待处理订单');
      return;
    }

    checkPendingOrdersActive(activePending, result.data, loadData());
  } catch (err) {
    console.error('[TRON检查] 轮询失败:', err.message);
  }
}

function checkPendingOrdersActive(pending, txList, data) {
  let matchCount = 0;

  for (const tx of txList) {
    if (tx.to !== CONFIG.trc20Address) continue;

    const txAmount = parseFloat(parseInt(tx.value, 10) || 0) / 1e6;

    for (const order of pending) {
      if (Math.abs(txAmount - order.displayAmount) < 0.001) {
        const orderData = data.orders[order.orderId];
        if (orderData && orderData.status === 'pending') {
          orderData.status = 'completed';
          orderData.txHash = tx.txID;
          orderData.completedAt = Date.now();

          const user = getOrCreateUser(order.userId);
          user.balance += order.credits;

          let referralBonus = 0;
          if (user.referrerId && order.baseAmount >= CONFIG.referralMinRecharge) {
            const referrer = data.users[user.referrerId];
            if (referrer) {
              referrer.balance += CONFIG.referralBonus;
              referrer.referralEarnings = (referrer.referralEarnings || 0) + CONFIG.referralBonus;
              referralBonus = CONFIG.referralBonus;
              addTx(user.referrerId, 'referral_bonus', CONFIG.referralBonus, `推荐返现: ${order.userId} 充值 ${order.baseAmount} USDT`);
            }
          }

          data.users[order.userId] = user;
          saveData(data);
          addTx(order.userId, 'recharge_complete', order.credits, 'USDT deposit confirmed', { orderId: order.orderId, txHash: tx.txID });

          const userMsg = `✅ **充值到账！**\n\n金额: *${order.displayAmount} USDT*\n到账积分: *${order.credits}*\n交易Hash: \`${tx.txID}\``;
          const adminMsg = `💰 **新充值到账！**\n\n用户: ${order.userId}\n金额: ${order.displayAmount} USDT\n积分: ${order.credits}\n订单: ${order.orderId}`;

          notifyTelegram(order.userId, userMsg);
          for (const adminId of CONFIG.admins) {
            notifyTelegram(adminId, adminMsg);
          }

          console.log(`[充值] 订单 ${order.orderId} 已到账 ${order.displayAmount} USDT`);
          matchCount++;
        }
      }
    }
  }

  if (matchCount > 0) {
    console.log(`[TRON检查] 匹配到 ${matchCount} 笔充值`);
  }
}

setInterval(checkPendingOrders, CONFIG.pollInterval);
setInterval(checkTronTransfers, CONFIG.tronPollInterval);
checkPendingOrders();
checkTronTransfers();

app.listen(CONFIG.port, () => {
  console.log(`Billing service running on port ${CONFIG.port}`);
  console.log(`TRC20 address: ${CONFIG.trc20Address}`);
  console.log(`1 USDT = ${CONFIG.rechargeRate} credits | ${CONFIG.imageCost} credits/image | ${CONFIG.newUserBonus} bonus credits`);
});
