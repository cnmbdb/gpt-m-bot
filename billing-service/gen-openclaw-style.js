#!/usr/bin/env node
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const OUTPUT_DIR = process.env.OUTPUT_DIR || '/tmp/codex-imagegen-service';
const API_KEY = process.env.OPENAI_API_KEY;
const MODEL = 'gpt-image-1';
const N = 1;

if (!API_KEY) {
  console.error('ERROR: OPENAI_API_KEY environment variable is required');
  process.exit(1);
}

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function apiRequest(payload) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const options = {
      hostname: 'api.openai.com',
      path: '/v1/images/generations',
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${API_KEY}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch {
          resolve(body);
        }
      });
    });

    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function downloadImage(url, filepath) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      const stream = fs.createWriteStream(filepath);
      res.pipe(stream);
      stream.on('finish', () => resolve(filepath));
      stream.on('error', reject);
    }).on('error', reject);
  });
}

async function generateImage(prompt, outputPath) {
  console.error(`[GEN] Generating image: ${prompt.substring(0, 80)}...`);

  const response = await apiRequest({
    model: MODEL,
    prompt: prompt,
    n: N,
    response_format: 'b64_json'
  });

  if (response.error) {
    throw new Error(response.error.message || JSON.stringify(response.error));
  }

  if (!response.data || !response.data[0]) {
    throw new Error('No image data returned from API');
  }

  const imageDataField = response.data[0].b64_json || response.data[0].url;
  if (!imageDataField) {
    throw new Error('No b64_json or url in response');
  }

  let imageData;
  if (response.data[0].b64_json) {
    imageData = Buffer.from(response.data[0].b64_json, 'base64');
  } else {
    // Download from URL
    imageData = await downloadImage(response.data[0].url, outputPath);
    console.error(`[GEN] Image downloaded from URL`);
    return imageData;
  }
  fs.writeFileSync(outputPath, imageData);
  console.error(`[GEN] Image saved to: ${outputPath}`);
  return outputPath;
}

// CLI entry point
const prompt = process.argv[2];
const outputPath = process.argv[3];

if (!prompt) {
  console.error('Usage: node gen-openclaw-style.js "<prompt>" [output_path]');
  process.exit(1);
}

ensureDir(OUTPUT_DIR);
const outFile = outputPath || path.join(OUTPUT_DIR, `gen_${Date.now()}.png`);

generateImage(prompt, outFile)
  .then(file => {
    console.log(file);
    process.exit(0);
  })
  .catch(err => {
    console.error('ERROR:', err.message);
    process.exit(1);
  });
