import {staticFile} from 'remotion';

// Managed media is served by InvocationAssetServer on loopback for the
// lifetime of one render. It is already a browser URL; passing it through
// staticFile() incorrectly treats it as a public-bundle-relative path.
const INVOCATION_ASSET_URL = /^https?:\/\/(?:127\.0\.0\.1|localhost):\d+(?:\/|$)/;

export const resolveInvocationAsset = (file: string): string =>
  INVOCATION_ASSET_URL.test(file) ? file : staticFile(file);
