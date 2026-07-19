'use strict';

/**
 * Regression test for a real deploy-breaking bug (PEN-228 PR review): Cloud
 * Functions / functions-framework discovers a --target (--entry-point) by
 * loading this package's `main` (index.js, per package.json) and looking up
 * the target's name in functions.http()'s registry. A function file that
 * defines `functions.http('someName', ...)` but is never require()'d from
 * index.js is unreachable at deploy time — `gcloud functions deploy
 * someName --entry-point someName` and `functions-framework
 * --target=someName` both fail to find it, even though the file itself,
 * and its own unit tests, are perfectly correct in isolation.
 *
 * This asserts every function name this repo actually deploys
 * (cloudbuild.yaml / package.json's deploy:* scripts / the GitHub Actions
 * workflow) ends up registered once index.js is loaded, so a future
 * function that forgets its `require('./new-thing')` line fails a test
 * instead of silently failing a real deploy.
 */

jest.mock('@google-cloud/functions-framework', () => ({
  http: jest.fn(),
}));

jest.mock('cors', () => () => (req, res, callback) => callback());

const EXPECTED_REGISTERED_FUNCTIONS = ['controlRobot', 'telemetryIngestion', 'unifiedIngress', 'healthLegPush'];

test('requiring index.js (the package main) registers every deployed Cloud Function', () => {
  jest.resetModules();
  const functions = require('@google-cloud/functions-framework');
  require('./index');

  const registeredNames = functions.http.mock.calls.map((call) => call[0]);
  for (const name of EXPECTED_REGISTERED_FUNCTIONS) {
    expect(registeredNames).toContain(name);
  }
});
