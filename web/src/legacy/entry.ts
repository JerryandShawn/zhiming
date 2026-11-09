import { followAcceptedLegacyRun } from './bridge';

declare global {
  interface Window {
    mingjingLegacyStream?: { followAccepted: typeof followAcceptedLegacyRun };
  }
}
// The old page opts in at send time. Loading this module never starts a query.
window.mingjingLegacyStream = { followAccepted: followAcceptedLegacyRun };
