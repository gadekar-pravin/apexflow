"""
Pydantic Schemas for UserModel Hubs

Defines the data models for:
- PreferencesHub (behavioral policies)
- OperatingContextHub (environment facts)
- SoftIdentityHub (personalization signals)
- EvidenceLog (audit trail)
- BeliefUpdateEngine (confidence/decay config)
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Common Types
# =============================================================================


class ConfidenceField(BaseModel):
    """A field with confidence tracking."""

    value: Any | None = None
    confidence: float = 0.0
    inferred_from: list[str] = Field(default_factory=list)
    last_seen_at: datetime | None = None


class ScopedValue(BaseModel):
    """A value that can vary by scope/domain."""

    default: Any | None = None
    by_scope: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    last_seen_at: datetime | None = None


class HubMeta(BaseModel):
    """Common metadata for all hubs."""

    confidence: float = 0.0
    evidence_count: int = 0
    last_updated: datetime | None = None
    created_at: datetime | None = None


# =============================================================================
# PreferencesHub Schemas
# =============================================================================


class StableDefaults(BaseModel):
    """User's stable default preferences."""

    default_language: str | None = "python"
    default_output_format: str | None = "markdown"
    default_verbosity: str | None = "concise"
    default_decision_style: str | None = "single_best"
    default_iteration_style: str | None = "fast_iterations"
    default_feedback_style: str | None = "implicit_ok"


class EmojiPolicy(BaseModel):
    """Emoji usage preferences."""

    mode: str | None = "minimal"
    allowed_when: list[str] = Field(default_factory=lambda: ["casual_chat"])
    disallowed_when: list[str] = Field(default_factory=lambda: ["work_artifacts"])


class ChunkingPolicy(BaseModel):
    """Code/content chunking preferences."""

    max_lines: int = 400
    prefer_full_files: bool = True
    chunk_strategy: str | None = "logical_sections"


class CitationsPosture(BaseModel):
    """Citation style preferences."""

    default: str | None = "minimal"
    by_scope: dict[str, str] = Field(default_factory=dict)
    style: str | None = "minimal_inline"


class QuestionsPolicy(BaseModel):
    """Clarification question preferences."""

    clarifications: str | None = "minimize"
    ask_only_if_blocked: bool = True
    if_ambiguous: str | None = "best_effort_assumptions"
    when_high_risk: str | None = "ask_before_irreversible"
    batch_questions: bool = True


class OptionsPresentation(BaseModel):
    """How to present options/alternatives."""

    default: str | None = "single_best"
    max_options: int = 3
    offer_options_when: list[str] = Field(default_factory=lambda: ["high_uncertainty"])


class OutputContract(BaseModel):
    """Output formatting and structure preferences."""

    verbosity: ScopedValue = Field(default_factory=lambda: ScopedValue(default="concise"))
    format_defaults: ScopedValue = Field(default_factory=lambda: ScopedValue(default="markdown"))
    structure_rules: list[str] = Field(default_factory=list)
    tone_constraints: list[str] = Field(default_factory=list)
    emoji_policy: EmojiPolicy = Field(default_factory=EmojiPolicy)
    chunking: ChunkingPolicy = Field(default_factory=ChunkingPolicy)
    citations_posture: CitationsPosture = Field(default_factory=CitationsPosture)
    questions_policy: QuestionsPolicy = Field(default_factory=QuestionsPolicy)
    options_presentation: OptionsPresentation = Field(default_factory=OptionsPresentation)


class AvoidPatterns(BaseModel):
    """Patterns to avoid in responses."""

    phrases: list[str] = Field(default_factory=list)
    moves: list[str] = Field(default_factory=list)


class NeverUse(BaseModel):
    """Words/phrases to never use."""

    words: list[str] = Field(default_factory=list)
    openings: list[str] = Field(default_factory=list)
    closings: list[str] = Field(default_factory=list)


class AntiPreferences(BaseModel):
    """Things to avoid."""

    avoid_patterns: AvoidPatterns = Field(default_factory=AvoidPatterns)
    never_use: NeverUse = Field(default_factory=NeverUse)


class FrameworkPrefs(BaseModel):
    """Framework preferences."""

    frontend: list[str] = Field(default_factory=list)
    backend: list[str] = Field(default_factory=list)
    testing: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class PackageManagerPrefs(BaseModel):
    """Package manager preferences."""

    python: str | None = "uv"
    javascript: str | None = "pnpm"
    confidence: float = 0.0


class StylePreferences(BaseModel):
    """Coding style preferences."""

    type_annotations: bool = True
    comment_density: str | None = "low"
    docstring_style: str | None = "google"
    line_length: int = 88
    import_style: str | None = "absolute"


class ToolingDefaults(BaseModel):
    """Default tooling preferences."""

    frameworks: FrameworkPrefs = Field(default_factory=FrameworkPrefs)
    package_manager: PackageManagerPrefs = Field(default_factory=PackageManagerPrefs)
    validation: list[str] = Field(default_factory=lambda: ["pydantic"])
    testing: list[str] = Field(default_factory=lambda: ["pytest"])
    preferred_libraries: dict[str, str] = Field(default_factory=dict)
    style_preferences: StylePreferences = Field(default_factory=StylePreferences)


class AutonomySettings(BaseModel):
    """What actions are allowed without confirmation."""

    create_files: str | None = "allowed"
    modify_files: str | None = "allowed"
    delete_files: str | None = "confirm_first"
    run_shell: str | None = "allowed"
    destructive_actions: str | None = "confirm_first"
    web_browse: str | None = "allowed"
    install_packages: str | None = "allowed"
    git_operations: str | None = "safe_only"


class RiskTolerance(BaseModel):
    """Risk tolerance by scope."""

    default: str | None = "moderate"
    by_scope: dict[str, str] = Field(default_factory=lambda: {"security": "conservative"})


class AutonomyAndRisk(BaseModel):
    """Autonomy and risk preferences."""

    autonomy: AutonomySettings = Field(default_factory=AutonomySettings)
    risk_tolerance: RiskTolerance = Field(default_factory=RiskTolerance)
    confirmation_gates: list[str] = Field(default_factory=list)


class CodingContracts(BaseModel):
    """Coding-specific preferences."""

    deliverable_preference: str | None = "full_file"
    error_handling_style: str | None = "explicit"
    async_preference: str | None = "async_first"
    testing_expectations: str | None = "unit_tests_required"


class PreferencesHubSchema(BaseModel):
    """Complete PreferencesHub schema."""

    hub_type: str = "PreferencesHub"
    schema_version: str = "1.0"
    stable_defaults: StableDefaults = Field(default_factory=StableDefaults)
    output_contract: OutputContract = Field(default_factory=OutputContract)
    anti_preferences: AntiPreferences = Field(default_factory=AntiPreferences)
    tooling_defaults: ToolingDefaults = Field(default_factory=ToolingDefaults)
    autonomy_and_risk: AutonomyAndRisk = Field(default_factory=AutonomyAndRisk)
    coding_contracts: CodingContracts = Field(default_factory=CodingContracts)
    meta: HubMeta = Field(default_factory=HubMeta)


# =============================================================================
# OperatingContextHub Schemas
# =============================================================================


class OSInfo(ConfidenceField):
    """Operating system information."""

    value: str | None = None
    version: str | None = None


class HardwareCPU(ConfidenceField):
    """CPU information."""

    architecture: str | None = None
    brand: str | None = None
    cores: int | None = None


class HardwareRAM(ConfidenceField):
    """RAM information."""

    value: int | None = None  # GB


class HardwareGPU(ConfidenceField):
    """GPU information."""

    value: str | None = None
    vram_gb: int | None = None


class HardwareInfo(BaseModel):
    """Hardware specs."""

    cpu: HardwareCPU = Field(default_factory=HardwareCPU)
    ram_gb: HardwareRAM = Field(default_factory=HardwareRAM)
    gpu: HardwareGPU = Field(default_factory=HardwareGPU)


class NetworkInfo(BaseModel):
    """Network constraints."""

    restricted: ConfidenceField = Field(default_factory=ConfidenceField)
    vpn_required: bool = False
    proxy_configured: bool = False


class EnvironmentInfo(BaseModel):
    """System environment."""

    os: OSInfo = Field(default_factory=OSInfo)
    shell: ConfidenceField = Field(default_factory=ConfidenceField)
    location_region: ConfidenceField = Field(default_factory=ConfidenceField)
    timezone: ConfidenceField = Field(default_factory=ConfidenceField)
    hardware: HardwareInfo = Field(default_factory=HardwareInfo)
    network: NetworkInfo = Field(default_factory=NetworkInfo)


class LanguagePrefs(ConfidenceField):
    """Programming language preferences."""

    ranked: list[str] = Field(default_factory=list)


class PackageManagerInfo(ConfidenceField):
    """Package manager info per language."""

    pass


class EditorInfo(BaseModel):
    """Editor/IDE info."""

    primary: str | None = None
    extensions: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class VersionControlInfo(BaseModel):
    """Version control setup."""

    tool: str | None = "git"
    hosting: str | None = None
    workflow: str | None = None
    confidence: float = 0.0


class DeveloperPosture(BaseModel):
    """Developer environment and preferences."""

    primary_languages: LanguagePrefs = Field(default_factory=LanguagePrefs)
    secondary_languages: list[str] = Field(default_factory=list)
    package_managers: dict[str, ConfidenceField] = Field(default_factory=dict)
    editor_ide: EditorInfo = Field(default_factory=EditorInfo)
    version_control: VersionControlInfo = Field(default_factory=VersionControlInfo)


class RuntimeEnv(BaseModel):
    """Runtime environment info."""

    version: str | None = None
    confidence: float = 0.0


class RuntimeEnvironments(BaseModel):
    """Available runtime environments."""

    python: RuntimeEnv = Field(default_factory=RuntimeEnv)
    node: RuntimeEnv = Field(default_factory=RuntimeEnv)
    docker: RuntimeEnv = Field(default_factory=RuntimeEnv)
    kubernetes: RuntimeEnv = Field(default_factory=RuntimeEnv)


class AssumptionLimits(BaseModel):
    """What to avoid assuming."""

    avoid_cuda_unless_confirmed: bool = True
    avoid_docker_unless_confirmed: bool = True
    avoid_cloud_cli_unless_confirmed: bool = True
    prefer_cross_platform_commands: bool = True


class ServiceAvailability(ConfidenceField):
    """Service availability status."""

    available: bool | None = None


class ServiceAccess(BaseModel):
    """External service access."""

    cloud_providers: dict[str, ServiceAvailability] = Field(default_factory=dict)
    databases: dict[str, ServiceAvailability] = Field(default_factory=dict)
    ai_services: dict[str, ServiceAvailability] = Field(default_factory=dict)


class OperatingContextHubSchema(BaseModel):
    """Complete OperatingContextHub schema."""

    hub_type: str = "OperatingContextHub"
    schema_version: str = "1.0"
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)
    developer_posture: DeveloperPosture = Field(default_factory=DeveloperPosture)
    runtime_environments: RuntimeEnvironments = Field(default_factory=RuntimeEnvironments)
    assumption_limits: AssumptionLimits = Field(default_factory=AssumptionLimits)
    service_access: ServiceAccess = Field(default_factory=ServiceAccess)
    meta: HubMeta = Field(default_factory=HubMeta)


# =============================================================================
# SoftIdentityHub Schemas
# =============================================================================


class DietaryStyle(ConfidenceField):
    """Dietary style preferences."""

    pass


class CuisineAffinities(BaseModel):
    """Cuisine preferences."""

    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    favorites: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    last_seen_at: datetime | None = None


class FoodRestrictions(BaseModel):
    """Food restrictions."""

    medical: list[str] = Field(default_factory=list)
    religious: list[str] = Field(default_factory=list)
    ethical: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class FoodAndDining(BaseModel):
    """Food preferences."""

    dietary_style: DietaryStyle = Field(default_factory=DietaryStyle)
    cuisine_affinities: CuisineAffinities = Field(default_factory=CuisineAffinities)
    restrictions: FoodRestrictions = Field(default_factory=FoodRestrictions)


class PetAffinity(ConfidenceField):
    """Pet affinity."""

    specific_breeds: list[str] = Field(default_factory=list)


class PetOwnership(BaseModel):
    """Pet ownership status."""

    current: bool | None = None
    past: bool | None = None
    pet_names: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    last_seen_at: datetime | None = None


class PetsAndAnimals(BaseModel):
    """Pet preferences."""

    affinity: PetAffinity = Field(default_factory=PetAffinity)
    ownership: PetOwnership = Field(default_factory=PetOwnership)


class ActivityLevel(ConfidenceField):
    """Activity level."""

    activities: list[str] = Field(default_factory=list)


class LifestyleAndWellness(BaseModel):
    """Lifestyle preferences."""

    activity_level: ActivityLevel = Field(default_factory=ActivityLevel)
    sleep_rhythm: ConfidenceField = Field(default_factory=ConfidenceField)
    travel_style: ConfidenceField = Field(default_factory=ConfidenceField)
    work_life_balance: ConfidenceField = Field(default_factory=ConfidenceField)


class MediaPrefs(BaseModel):
    """Media preferences."""

    genres: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class MediaAndEntertainment(BaseModel):
    """Media preferences."""

    music: MediaPrefs = Field(default_factory=MediaPrefs)
    books: MediaPrefs = Field(default_factory=MediaPrefs)
    movies_tv: MediaPrefs = Field(default_factory=MediaPrefs)
    podcasts: MediaPrefs = Field(default_factory=MediaPrefs)
    content_depth: ConfidenceField = Field(default_factory=ConfidenceField)


class CommunicationStyle(BaseModel):
    """Communication style preferences."""

    humor_tolerance: ConfidenceField = Field(default_factory=ConfidenceField)
    small_talk_tolerance: ConfidenceField = Field(default_factory=ConfidenceField)
    metaphor_preference: ConfidenceField = Field(default_factory=ConfidenceField)
    formality_preference: ConfidenceField = Field(default_factory=ConfidenceField)


class InterestsAndHobbies(BaseModel):
    """User interests."""

    professional_interests: list[str] = Field(default_factory=list)
    personal_hobbies: list[str] = Field(default_factory=list)
    learning_interests: list[str] = Field(default_factory=list)
    side_projects: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ProfessionalContext(BaseModel):
    """Professional context."""

    industry: ConfidenceField = Field(default_factory=ConfidenceField)
    role_type: ConfidenceField = Field(default_factory=ConfidenceField)
    experience_level: ConfidenceField = Field(default_factory=ConfidenceField)
    team_size: ConfidenceField = Field(default_factory=ConfidenceField)


class SoftIdentityUsageRules(BaseModel):
    """Usage rules for soft identity data."""

    allowed_in: list[str] = Field(default_factory=lambda: ["examples", "casual_chat", "analogies"])
    never_affects: list[str] = Field(default_factory=lambda: ["tool_selection", "risk_decisions", "security_choices"])
    never_infer_identity: bool = True
    never_assume_values: bool = True
    never_use_for_persuasion: bool = True


class SoftIdentityHubSchema(BaseModel):
    """Complete SoftIdentityHub schema."""

    hub_type: str = "SoftIdentityHub"
    schema_version: str = "1.0"
    food_and_dining: FoodAndDining = Field(default_factory=FoodAndDining)
    pets_and_animals: PetsAndAnimals = Field(default_factory=PetsAndAnimals)
    lifestyle_and_wellness: LifestyleAndWellness = Field(default_factory=LifestyleAndWellness)
    media_and_entertainment: MediaAndEntertainment = Field(default_factory=MediaAndEntertainment)
    communication_style: CommunicationStyle = Field(default_factory=CommunicationStyle)
    interests_and_hobbies: InterestsAndHobbies = Field(default_factory=InterestsAndHobbies)
    professional_context: ProfessionalContext = Field(default_factory=ProfessionalContext)
    usage_rules: SoftIdentityUsageRules = Field(default_factory=SoftIdentityUsageRules)
    extras: dict[str, Any] = Field(default_factory=dict)
    meta: HubMeta = Field(default_factory=HubMeta)


# =============================================================================
# EvidenceLog Schemas
# =============================================================================


class EvidenceSource(BaseModel):
    """Source of an evidence event."""

    type: str  # conversation|notes|browser|project|system|news|manual
    reference: str | None = None  # session_id, file_path, or url
    context: str | None = None


class SignalType(BaseModel):
    """Type and strength of a signal."""

    category: (
        str  # explicit_preference|implicit_behavior|correction|rejection|acceptance|context_signal|system_observation
    )
    strength: str = "medium"  # strong|medium|weak


class DerivedUpdate(BaseModel):
    """An update derived from evidence."""

    target_hub: str  # PreferencesHub|OperatingContextHub|SoftIdentityHub
    target_path: str  # dot-separated path like "output_contract.verbosity.by_scope.coding"
    operation: str  # set|increment|decrement|add_to_list|remove_from_list
    old_value: Any | None = None
    new_value: Any | None = None
    confidence_delta: float = 0.1


class EvidenceEvent(BaseModel):
    """A single evidence event."""

    event_id: str
    timestamp: datetime
    source: EvidenceSource
    signal_type: SignalType
    raw_excerpt: str
    excerpt_hash: str | None = None
    derived_updates: list[DerivedUpdate] = Field(default_factory=list)
    confidence_impact: float = 0.1
    decay_group: str = "recency_sensitive"  # stable|recency_sensitive|fast_decay


class SignalTypeTaxonomy(BaseModel):
    """Configuration for signal types."""

    description: str
    indicators: list[str] = Field(default_factory=list)
    base_confidence: float = 0.3
    decay_rate: str = "medium"


class RetentionPolicy(BaseModel):
    """Evidence retention policy."""

    store_full_excerpts: bool = False
    max_excerpt_length: int = 200
    max_events: int = 1000
    prune_strategy: str = "oldest_first"
    merge_similar_events: bool = True
    archive_after_days: int = 90


class EvidenceLogMeta(BaseModel):
    """Evidence log metadata."""

    total_events: int = 0
    events_by_source: dict[str, int] = Field(default_factory=dict)
    events_by_type: dict[str, int] = Field(default_factory=dict)
    last_pruned_at: datetime | None = None


class EvidenceLogSchema(BaseModel):
    """Complete EvidenceLog schema."""

    hub_type: str = "EvidenceLog"
    schema_version: str = "1.0"
    events: list[EvidenceEvent] = Field(default_factory=list)
    signal_type_taxonomy: dict[str, SignalTypeTaxonomy] = Field(default_factory=dict)
    retention_policy: RetentionPolicy = Field(default_factory=RetentionPolicy)
    meta: EvidenceLogMeta = Field(default_factory=EvidenceLogMeta)


# =============================================================================
# BeliefUpdateEngine Schemas
# =============================================================================


class PriorityLevel(BaseModel):
    """Priority level configuration."""

    weight: float = 0.6
    immune_to_decay: bool = False
    requires_explicit_override: bool = False


class ConfidenceConfig(BaseModel):
    """Confidence update configuration."""

    base: float = 0.3
    increment_per_evidence: float = 0.1
    decrement_on_contradiction: float = 0.15
    cap: float = 0.95
    floor: float = 0.1


class RecencyDecayConfig(BaseModel):
    """Recency decay configuration."""

    enabled: bool = True
    half_life_days: int = 90
    exclude_priorities: list[str] = Field(default_factory=list)
    minimum_after_decay: float = 0.2


class EvidenceThresholds(BaseModel):
    """Evidence thresholds for confidence levels."""

    tentative: int = 1
    established: int = 3
    confident: int = 5


class HubConfig(BaseModel):
    """Configuration for a specific hub."""

    confidence: ConfidenceConfig = Field(default_factory=ConfidenceConfig)
    recency_decay: RecencyDecayConfig = Field(default_factory=RecencyDecayConfig)
    evidence_thresholds: EvidenceThresholds = Field(default_factory=EvidenceThresholds)


class GlobalRules(BaseModel):
    """Global belief update rules."""

    conflict_resolution_order: list[str] = Field(
        default_factory=lambda: [
            "prefer_higher_priority",
            "prefer_more_specific_scope",
            "prefer_more_recent",
            "prefer_higher_confidence",
        ]
    )
    default_priority: str = "soft"
    priority_levels: dict[str, PriorityLevel] = Field(
        default_factory=lambda: {
            "hard": PriorityLevel(weight=1.0, immune_to_decay=True, requires_explicit_override=True),
            "soft": PriorityLevel(weight=0.6),
            "situational": PriorityLevel(weight=0.3),
        }
    )
    minimum_evidence_to_persist: int = 1
    contradiction_handling: str = "create_scoped_variant"


class ScopeHierarchy(BaseModel):
    """Scope hierarchy configuration."""

    levels: list[str] = Field(default_factory=lambda: ["global", "domain", "project", "session"])
    inheritance: str = "narrower_overrides_broader"
    domains: list[str] = Field(
        default_factory=lambda: ["coding", "teaching", "planning", "research", "writing", "debugging", "ops"]
    )


class BeliefUpdateEngineSchema(BaseModel):
    """Complete BeliefUpdateEngine schema."""

    engine_type: str = "BeliefUpdateEngine"
    schema_version: str = "1.0"
    global_rules: GlobalRules = Field(default_factory=GlobalRules)
    per_hub_config: dict[str, HubConfig] = Field(
        default_factory=lambda: {
            "PreferencesHub": HubConfig(
                confidence=ConfidenceConfig(base=0.5, cap=0.95, floor=0.2),
                recency_decay=RecencyDecayConfig(half_life_days=90, exclude_priorities=["hard"]),
            ),
            "OperatingContextHub": HubConfig(
                confidence=ConfidenceConfig(base=0.4, increment_per_evidence=0.15, decrement_on_contradiction=0.25),
                recency_decay=RecencyDecayConfig(half_life_days=120),
            ),
            "SoftIdentityHub": HubConfig(
                confidence=ConfidenceConfig(base=0.3, cap=0.8), recency_decay=RecencyDecayConfig(half_life_days=60)
            ),
        }
    )
    scope_hierarchy: ScopeHierarchy = Field(default_factory=ScopeHierarchy)


# =============================================================================
# BrowsingHistoryStore Schemas
# =============================================================================


class BrowsingVisit(BaseModel):
    """A single browsing visit."""

    visit_id: str
    url: str
    title: str | None = None
    domain: str | None = None
    source: str = "direct_browse"  # news_feed|direct_browse|search_result|link_click
    timestamp: datetime
    dwell_time_seconds: int | None = None
    scroll_depth: float | None = None
    content_extracted: bool = False
    content_hash: str | None = None


class ContentCacheItem(BaseModel):
    """Cached content from a visited page."""

    content_id: str
    visit_id: str
    url: str
    title: str | None = None
    extracted_text: str | None = None
    word_count: int | None = None
    extracted_at: datetime
    categories: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    summary: str | None = None


class BrowsingAggregations(BaseModel):
    """Aggregated browsing statistics."""

    domains_by_visit_count: dict[str, int] = Field(default_factory=dict)
    categories_by_time_spent: dict[str, int] = Field(default_factory=dict)
    reading_times_by_hour: dict[int, int] = Field(default_factory=dict)
    content_depth_distribution: dict[str, int] = Field(default_factory=dict)


class BrowsingRetentionPolicy(BaseModel):
    """Browsing history retention policy."""

    max_visits: int = 10000
    max_content_items: int = 500
    prune_visits_after_days: int = 90
    prune_content_after_days: int = 30


class BrowsingHistoryStoreSchema(BaseModel):
    """Complete BrowsingHistoryStore schema."""

    store_type: str = "BrowsingHistoryStore"
    schema_version: str = "1.0"
    visits: list[BrowsingVisit] = Field(default_factory=list)
    content_cache: list[ContentCacheItem] = Field(default_factory=list)
    aggregations: BrowsingAggregations = Field(default_factory=BrowsingAggregations)
    retention_policy: BrowsingRetentionPolicy = Field(default_factory=BrowsingRetentionPolicy)
