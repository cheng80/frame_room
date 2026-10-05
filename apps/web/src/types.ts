export type Point={x:number;y:number};
export type Rect=Point & {width:number;height:number};
export type RGBA=[number,number,number,number];
export interface Asset {assetId:string;sha256:string;decodedHash:string;originalFilename:string;mediaType:string;width:number;height:number;role:string;alphaStats:{transparent:number;partial:number;opaque:number};provenance:unknown;url:string}
export interface Video {videoId:string;sha256:string;originalFilename:string;mediaType:string;width:number;height:number;fps:number;frameCount:number;durationMs:number;timesMs?:number[];streamIndex?:number;provenance:unknown;url:string}
export interface Frame {frameId:string;frameVersionId:string;parentFrameVersionId?:string;rawAssetId:string;imageAssetId:string;sourceRect:Rect;sourceToFrameTransform:{scaleX:number;scaleY:number;offsetX:number;offsetY:number};extractionVersion:string;extractionReview?:{componentIndex?:number;area?:number;belowMinArea?:boolean;warnings?:unknown[];rect?:Rect};nativeScaleGroupId:string;review:string;reviewReason?:string;hidden:boolean}
export interface Group {alignmentGroupId:string;groupRevisionId:string;frameVersionIds:string[];mode:string;sharedScale:number;cell:{width:number;height:number;edge:number};targetAnchor:Point;bodyMeasurement:null|{topY:number;bottomY:number;targetHeight:number;approved:boolean};resampler:string;roundingVersion:string}
export interface Alignment {frameVersionId:string;groupRevisionId:string;sourceAnchor:Point;anchorSpace:string;method:string;contactMode:string;rootAnchor?:Point;authoredOffsetPx:Point;approval:string;reviewInvalidatedReason?:string}
export interface Transform {dx:number;dy:number;scaleX:number;scaleY:number;rotationDeg:number;shearX:number;shearY:number;flipX:boolean;flipY:boolean;pivot:Point}
export interface PixelEdit extends Point {color:RGBA}
export interface Occurrence {occurrenceId:string;frameVersionId:string;durationMs:number;timingMode:string;transform:Transform;pixelEdits:PixelEdit[]}
export interface Clip {sourceVideoId?:string;clipId:string;clipRevisionId:string;name:string;stateId:string;facing:string;referenceRevisionId:string|null;loop:boolean;endBehavior:string;defaultFps:number;occurrences:Occurrence[];review:string;reviewInvalidatedReason?:string}
export interface Reference {referenceRevisionId:string;identityAssetId:string;styleAssetIds:string[];poseAssetIds:string[];fixedTraits:string;allowedChanges:string;forbiddenTransfers:string;facing:string;bodyMeasurement:unknown;approval:string}
export interface Outline {enabled:boolean;mode:string;teamLabel:string;colorRGBA:RGBA;thicknessPx:number;directions:number;opacityPerCopy:number;rendererVersion:string}
export interface ProjectStorage {layout:'project-folder';path:string;available:boolean;syncPending?:boolean}
export interface MissingProjectFolder {projectId:string;name:string;path:string;revision:number}
export interface Snapshot {projectId:string;storage?:ProjectStorage;schemaVersion:number;revision:number;name:string;characterName:string;createdAt:string;updatedAt:string;assets:Asset[];videos?:Video[];references:Reference[];activeReferenceRevisionId:string|null;frames:Frame[];alignmentGroups:Group[];alignments:Record<string,Alignment>;clips:Clip[];outline:Outline;generationSettings:Record<string,unknown>;journal:unknown[];generations:unknown[]}
export type Operation={type:string;[key:string]:any};
export interface DraftCommand {operation:Operation;localId?:string}
export interface Artifact {artifactId:string;name:string;url:string;mediaType?:string;sha256?:string}
/** Optional additions: older saved jobs may contain none of these diagnostics. */
export interface VideoFootStrike extends Record<string, unknown> {
  start?: number; start_foot?: 'left' | 'right' | null; start_foot_source?: string | null;
  foot_why?: string; candidates?: number[]; strikes?: number[];
}
export interface VideoResample extends Record<string, unknown> {
  made?: number; nearest?: number; made_by_rife?: number; made_at?: number[]; nearest_at?: number[];
  smear?: {at?: number; method?: string; faults?: string[]}[];
}
export interface VideoProcessingResult extends Record<string, unknown> {
  source?: Record<string, unknown> & {timesMs?: number[]; streamIndex?: number};
  selection?: Record<string, unknown> & {
    period?: Record<string, unknown> & {suspect?: boolean; reason?: string; suspects?: unknown[]};
    held?: Record<string, unknown> & {hold?: number | null; drawings_per_second?: number | null};
    footStrike?: VideoFootStrike;
    sizeHold?: Record<string, unknown> & {applied?: boolean; drift?: number};
    retake?: Record<string, unknown> & {suggested?: boolean; reasons?: unknown[]};
    alignment?: Record<string, unknown> & {resample?: VideoResample; footStrike?: VideoFootStrike};
    cycleAlignment?: VideoResample & {footStrike?: VideoFootStrike; turnedBy?: number; outputMadeAt?: number[]; outputNearestAt?: number[]; indexSpace?: string};
    outputPhase?: {turnedBy?: number; manual?: boolean; footStrike?: VideoFootStrike};
  };
}
export interface Job {jobId:string;batchId?:string;batchIndex?:number;batchSize?:number;inspectionClipIds?:string[];operation:string;status:string;step?:string;failedStep?:string;inputRevision:number;progress?:number|{percent?:number;message?:string};errors?:{code?:string;message?:string}[];error?:{code?:string;message?:string};artifacts?:Artifact[];result?:{qa?:unknown;manifest?:Runtime;projectId?:string;frameVersionIds?:string[];videoId?:string;clipId?:string;processing?:VideoProcessingResult};resumable?:boolean;createdAt?:string}
export interface Health {api:string;worker:string;engine?:{version:string;commit:string};sessionToken:string;limits?:{maxUploadBytes?:number};desktop?:{fileManager:'finder'|'explorer'|null}}
export interface Provider {providerId:string;mediaKind?:'image'|'video';name?:string;label?:string;available?:boolean;loginReady?:boolean;reason?:string;disabledReason?:string;models?:(string|{id:string;name?:string})[];model?:string;defaultModel?:string;capabilities?:Record<string,any>;billingRoute?:string;quota?:unknown;lastSuccess?:unknown}
export interface Runtime {schemaVersion:number;exportId:string;projectRevision:number;recipeHash?:string;atlas:{file:string;sha256?:string;width:number;height:number};frames:{id:string;frameVersionId?:string;rect:Rect;anchor:[number,number]}[];clips:{id:string;name?:string;loop:boolean;endBehavior:string;occurrences:{id:string;renderedFrameId:string;durationMs:number}[]}[]}
export interface ExportRecord {exportId:string;jobId?:string;status:string;errors?:{code?:string;message?:string}[];manifest?:Runtime;files?:Artifact[];projectRevision?:number}
export const defaultTransform=(pivot:Point={x:256,y:256}):Transform=>({dx:0,dy:0,scaleX:1,scaleY:1,rotationDeg:0,shearX:0,shearY:0,flipX:false,flipY:false,pivot});
export const uid=()=>crypto.randomUUID();
