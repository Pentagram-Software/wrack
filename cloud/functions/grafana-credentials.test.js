'use strict';

/**
 * Unit tests for grafana-credentials.js (PEN-228). Strategy mirrors
 * ingress.js's device-tokens tests: mock @google-cloud/secret-manager and
 * control Date.now() to exercise the TTL cache.
 */

let mockAccessSecretVersion;

jest.mock('@google-cloud/secret-manager', () => ({
  SecretManagerServiceClient: jest.fn().mockImplementation(() => ({
    accessSecretVersion: (...args) => mockAccessSecretVersion(...args),
  })),
}));

const {
  getGrafanaCredentials,
  _isValidCredentialsShape,
  _resetCredentialsCache,
} = require('./grafana-credentials');

const VALID_CREDENTIALS = {
  otlp_endpoint: 'https://otlp-gateway-prod-xx-xxxx.grafana.net/otlp',
  instance_id: '123456',
  token: 'glc_test_token',
};

function mockSecretPayload(value) {
  return jest.fn().mockResolvedValue([{ payload: { data: Buffer.from(JSON.stringify(value)) } }]);
}

beforeEach(() => {
  _resetCredentialsCache();
  mockAccessSecretVersion = mockSecretPayload(VALID_CREDENTIALS);
});

describe('_isValidCredentialsShape()', () => {
  test('true for a well-formed credentials object', () => {
    expect(_isValidCredentialsShape(VALID_CREDENTIALS)).toBe(true);
  });

  test.each([
    ['null', null],
    ['an array', ['a']],
    ['a string', 'nope'],
    ['missing otlp_endpoint', { instance_id: '1', token: 't' }],
    ['empty otlp_endpoint', { otlp_endpoint: '', instance_id: '1', token: 't' }],
    ['missing instance_id', { otlp_endpoint: 'https://x', token: 't' }],
    ['non-string instance_id', { otlp_endpoint: 'https://x', instance_id: 123, token: 't' }],
    ['missing token', { otlp_endpoint: 'https://x', instance_id: '1' }],
    ['empty token', { otlp_endpoint: 'https://x', instance_id: '1', token: '' }],
  ])('false for %s', (_label, value) => {
    expect(_isValidCredentialsShape(value)).toBe(false);
  });
});

describe('getGrafanaCredentials()', () => {
  test('returns the parsed secret payload', async () => {
    await expect(getGrafanaCredentials()).resolves.toEqual(VALID_CREDENTIALS);
  });

  test('reads from the projects/<project>/secrets/<secret>/versions/latest path', async () => {
    await getGrafanaCredentials();
    expect(mockAccessSecretVersion).toHaveBeenCalledWith({
      name: expect.stringMatching(/^projects\/.+\/secrets\/grafana-cloud-push-credentials\/versions\/latest$/),
    });
  });

  test('a second call in the same warm instance does not re-fetch the secret', async () => {
    await getGrafanaCredentials();
    await getGrafanaCredentials();
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(1);
  });

  test('re-fetches once the cache TTL has elapsed, picking up a rotated token', async () => {
    const nowSpy = jest.spyOn(Date, 'now');
    nowSpy.mockReturnValue(1_000_000);

    await getGrafanaCredentials();
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(1);

    mockAccessSecretVersion = mockSecretPayload({ ...VALID_CREDENTIALS, token: 'glc_rotated_token' });

    // Still within the TTL — cached value wins, rotation not observed yet.
    nowSpy.mockReturnValue(1_000_000 + 60 * 1000);
    const stillCached = await getGrafanaCredentials();
    expect(stillCached.token).toBe('glc_test_token');
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(0);

    // Past the TTL — re-fetches and picks up the rotated token.
    nowSpy.mockReturnValue(1_000_000 + 6 * 60 * 1000);
    const rotated = await getGrafanaCredentials();
    expect(rotated.token).toBe('glc_rotated_token');
    expect(mockAccessSecretVersion).toHaveBeenCalledTimes(1);

    nowSpy.mockRestore();
  });

  test('rejects (never caches) when the secret payload is malformed JSON', async () => {
    mockAccessSecretVersion = jest.fn().mockResolvedValue([{ payload: { data: Buffer.from('not json') } }]);
    await expect(getGrafanaCredentials()).rejects.toThrow();
    // A subsequent call must try again, not silently trust a null/undefined cache.
    mockAccessSecretVersion = mockSecretPayload(VALID_CREDENTIALS);
    await expect(getGrafanaCredentials()).resolves.toEqual(VALID_CREDENTIALS);
  });

  test('rejects with a descriptive error when the secret has the wrong shape', async () => {
    mockAccessSecretVersion = mockSecretPayload({ instance_id: '1', token: 't' });
    await expect(getGrafanaCredentials()).rejects.toThrow(/unexpected shape/);
  });

  test('propagates a Secret Manager access failure (e.g. missing IAM grant)', async () => {
    mockAccessSecretVersion = jest.fn().mockRejectedValue(new Error('PERMISSION_DENIED'));
    await expect(getGrafanaCredentials()).rejects.toThrow('PERMISSION_DENIED');
  });
});
