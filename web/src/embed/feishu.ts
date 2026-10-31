export type ContainerHost = 'browser' | 'feishu';
export type TrustedAdapterProbe = () => ContainerHost | null | undefined;
export type ContainerDetection = {
  host: ContainerHost;
  evidence: {
    source: 'user-agent' | 'trusted-adapter';
    adapter: 'not-provided' | 'reported' | 'unavailable' | 'failed';
    matchedToken?: 'lark' | 'feishu';
  };
  auth: { readonly status: 'not-connected' };
};

const disconnectedAuth = Object.freeze({ status: 'not-connected' as const });

/** Container appearance is a hint only; it never establishes identity or authentication. */
export function detectContainer(userAgent: string, trustedAdapterProbe?: TrustedAdapterProbe): ContainerDetection {
  let adapter: ContainerDetection['evidence']['adapter'] = 'not-provided';
  if (trustedAdapterProbe) {
    try {
      const host = trustedAdapterProbe();
      if (host === 'feishu' || host === 'browser')
        return { host, evidence: { source: 'trusted-adapter', adapter: 'reported' }, auth: disconnectedAuth };
      adapter = 'unavailable';
    } catch {
      adapter = 'failed';
    }
  }
  const match = /\b(Lark|Feishu)\b/i.exec(userAgent);
  const matchedToken = match?.[1].toLowerCase() as 'lark' | 'feishu' | undefined;
  return {
    host: matchedToken ? 'feishu' : 'browser',
    evidence: { source: 'user-agent', adapter, ...(matchedToken ? { matchedToken } : {}) },
    auth: disconnectedAuth,
  };
}

/** Deliberate disconnected placeholder: no SDK, transport, credentials or token input. */
export const disconnectedSignInPort = Object.freeze({
  available: false as const,
  status: 'not-connected' as const,
  async request() {
    return { status: 'unavailable' as const, reason: 'not-connected' as const };
  },
});
