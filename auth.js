const crypto = require('crypto');

const API_KEY = process.env.API_KEY || 'your-secret-api-key';
const RATE_LIMIT_WINDOW = 60000; // 1 minute
const MAX_REQUESTS_PER_WINDOW = 100;

const requestCounts = new Map();

function validateApiKey(req) {
  const apiKey = req.headers['x-api-key'] || req.headers['authorization']?.replace('Bearer ', '');
  
  if (!apiKey) {
    throw new Error('API key is required');
  }
  
  if (apiKey !== API_KEY) {
    throw new Error('Invalid API key');
  }
  
  return true;
}

function rateLimitCheck(clientId) {
  const now = Date.now();
  const windowStart = now - RATE_LIMIT_WINDOW;
  
  if (!requestCounts.has(clientId)) {
    requestCounts.set(clientId, []);
  }
  
  const requests = requestCounts.get(clientId);
  
  const recentRequests = requests.filter(timestamp => timestamp > windowStart);
  
  if (recentRequests.length >= MAX_REQUESTS_PER_WINDOW) {
    throw new Error('Rate limit exceeded. Please try again later.');
  }
  
  recentRequests.push(now);
  requestCounts.set(clientId, recentRequests);
  
  setTimeout(() => {
    if (requestCounts.has(clientId)) {
      const updatedRequests = requestCounts.get(clientId).filter(timestamp => timestamp > Date.now() - RATE_LIMIT_WINDOW);
      if (updatedRequests.length === 0) {
        requestCounts.delete(clientId);
      } else {
        requestCounts.set(clientId, updatedRequests);
      }
    }
  }, RATE_LIMIT_WINDOW);
  
  return true;
}

function getClientId(req) {
  const forwardedFor = req.headers['x-forwarded-for'];
  const clientIp = forwardedFor ? forwardedFor.split(',')[0].trim() : req.connection.remoteAddress;
  
  const userAgent = req.headers['user-agent'] || 'unknown';
  
  return crypto.createHash('sha256').update(clientIp + userAgent).digest('hex');
}

function authenticateRequest(req) {
  validateApiKey(req);
  
  const clientId = getClientId(req);
  rateLimitCheck(clientId);
  
  return { clientId, authenticated: true };
}

module.exports = {
  authenticateRequest,
  validateApiKey,
  rateLimitCheck,
  getClientId
};