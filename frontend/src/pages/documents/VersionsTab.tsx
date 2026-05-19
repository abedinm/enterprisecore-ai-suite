import { ComingSoon } from '../../components/ComingSoon';

export function VersionsTab() {
  return (
    <ComingSoon
      title="Version history"
      description="Every edit auto-snapshots; restore any prior version. Backend at /api/v1/documents/{id}/versions and /restore is live."
    />
  );
}
