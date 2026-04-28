#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const DATA_FILE = path.join(__dirname, 'data', 'billing.json');
const ADMIN_IDS = ['825512163', '8277934317'];

function loadData() {
  try {
    return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  } catch {
    return { users: {}, orders: {} };
  }
}

const userId = process.argv[2];
if (!userId) {
  console.log(JSON.stringify({ allowed: false, reason: 'no_user_id' }));
  process.exit(0);
}

// Admins are always allowed
if (ADMIN_IDS.includes(userId)) {
  console.log(JSON.stringify({ allowed: true }));
  process.exit(0);
}

const data = loadData();
const user = data.users[userId];

// New user (no balance record yet) -> allowed
if (!user) {
  console.log(JSON.stringify({ allowed: true }));
  process.exit(0);
}

// Balance check: must have at least 50 credits for image generation
if (user.balance < 50) {
  console.log(JSON.stringify({ allowed: false, reason: 'daily_limit', balance: user.balance }));
  process.exit(0);
}

// Count completed image generation orders today
const today = new Date();
today.setHours(0, 0, 0, 0);
const todayOrders = Object.values(data.orders).filter(o =>
  o.userId === userId &&
  o.status === 'completed' &&
  o.completedAt >= today.getTime() &&
  o.coin === 'IMAGE'
);

if (todayOrders.length >= 5) {
  console.log(JSON.stringify({ allowed: false, reason: 'rate_limit', balance: user.balance }));
  process.exit(0);
}

console.log(JSON.stringify({ allowed: true, balance: user.balance }));
