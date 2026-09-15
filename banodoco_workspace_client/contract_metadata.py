"""PR90 base contract metadata plus an explicitly vendored backport.

SCHEMA_DIGEST and COMPONENT_MANIFEST_SHA256 retain the base artifact's pins;
OPERATIONS describes the shipped client including the backport. No combined
upstream schema or generation provenance is claimed.
"""

PROTOCOL = "workspace.v1"
COMPONENT_MANIFEST_SHA256 = 'sha256:dc91a45390f33582f0299f81285d165128e1885a9fd62b4ccffa7b8e465ed63a'
SCHEMA_DIGEST = 'sha256:2043e7bc9b06fc19e20906aff8eaa429fcb8ab335bedc31bd34bff9ab5b71b75'
OPERATIONS = ('health', 'handshake', 'getRealm', 'doctor', 'createBackup', 'restoreBackup', 'exportRealm', 'tombstoneRealm', 'recoverRealm', 'purgeRealm', 'listProjects', 'createProject', 'getProject', 'updateProject', 'currentProject', 'selectProject', 'listDocuments', 'createDocument', 'getDocument', 'updateDocument', 'listProjectObjects', 'ingestProjectObject', 'getProjectObjectLocation', 'listProjectTasks', 'listManagedOutputs', 'getManagedOutput', 'adoptManagedOutput', 'exportManagedOutput', 'updateManagedOutputLifecycle', 'listProjectRuns', 'createTimeline', 'listTimelines', 'createTimelineDocument', 'getTimeline', 'updateTimeline', 'listTimelineHistory', 'replaceTimelineClip', 'diffTimeline', 'archiveTimeline', 'recoverTimeline', 'createShot', 'getShot', 'updateShot', 'archiveShot', 'recoverShot', 'createReference', 'createProjectShot', 'listProjectShots', 'getProjectShot', 'updateProjectShot', 'archiveProjectShot', 'recoverProjectShot', 'addShotItem', 'removeShotItem', 'promoteProjectShotCandidate', 'reorderShotItems', 'listProjectShotTextBindings', 'setProjectShotTextBinding', 'getProjectShotTextBinding', 'setProjectShotTextBindingById', 'rebindProjectShotTextBinding', 'createProjectReference', 'listProjectReferences', 'getProjectReference', 'updateProjectReference', 'archiveProjectReference', 'recoverProjectReference', 'associateReference', 'setPrimaryReference', 'linkReferences', 'getReference', 'updateReference', 'archiveReference', 'recoverReference', 'listMediaRelations', 'createMediaRelation', 'ingestObject', 'getObject', 'headObject', 'admitTask', 'claimTask', 'getTask', 'cancelTask', 'retryTask', 'getRun', 'cancelRun', 'retryRun', 'listRunEvents', 'listEvents', 'registerExecutor', 'listCapabilities', 'registerCapability', 'listGenerations', 'createGeneration', 'getGeneration', 'listVariants', 'createVariant', 'getVariant', 'settleAttempt', 'prepareReboot', 'checkpointAttempt', 'publishTimelineRender', 'failAttempt', 'heartbeatAttempt', 'requestReboot', 'resumeAttempt')

# Exact source artifacts; the PR base has no verified upstream commit pin.
SOURCE_REPOSITORY = "https://github.com/banodoco/banodoco-workspace-runtime.git"
BASE_ASTRID_COMMIT = "cf7f9934d0fb7434dcbfff49292750c29bfeac97"
BASE_GENERATED_CLIENT_SHA256 = "sha256:6f98f414f19848d477675b8483edacc3dc51b74c549466a29102cc7572f45d7e"
# Main's old upstream pin did not contain this API; the local runtime source
# was modified. Pin the verified Astrid artifact instead of claiming upstream
# generation from that commit.
OBJECT_LOCATION_ASTRID_COMMIT = "efff68c95b515ac9dc764cb81b59e8e3b7987eba"
OBJECT_LOCATION_SOURCE_SCHEMA_DIGEST = "sha256:fd1fa0185ecdf183e1f42d25c2d933bc5c110ad609dbdc86a458d6f7e5dc0eec"
OBJECT_LOCATION_SOURCE_CLIENT_SHA256 = "sha256:4a7642d6b71c7d16689f48914a40c3331c21b4299884cc6570925beeb89c033e"
VENDORED_BACKPORT_OPERATIONS = ("getProjectObjectLocation",)
