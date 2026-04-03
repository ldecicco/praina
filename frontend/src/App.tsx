import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Toaster, toast } from "sonner";
import { CommandPalette } from "./components/CommandPalette";
import type { CommandItem } from "./components/CommandPalette";
import { GuidedTour } from "./components/GuidedTour";
import type { GuidedTourStep } from "./components/GuidedTour";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faBarsStaggered,
  faBell,
  faBook,
  faCalendarDay,
  faChartLine,
  faChevronDown,
  faChevronLeft,
  faChevronRight,
  faClipboardCheck,
  faComments,
  faGear,
  faLayerGroup,
  faPen,
  faRightFromBracket,
  faSearch,
  faLightbulb,
  faSitemap,
  faSquareCheck,
  faUserShield,
  faFileLines,
  faFlask,
  faGraduationCap,
  faUsers,
  faWrench,
  faXmark,
  faBug,
  faPlus,
  faArrowLeft,
  faCircle,
} from "@fortawesome/free-solid-svg-icons";

import { AdminPanel } from "./components/AdminPanel";
import { AssignmentMatrix } from "./components/AssignmentMatrix";
import { AuthScreen } from "./components/AuthScreen";
import { ChatWorkspace } from "./components/ChatWorkspace";
import { DeliveryBoard } from "./components/DeliveryBoard";
import { DeliverableWorkbench } from "./components/DeliverableWorkbench";
import { DocumentLibrary } from "./components/DocumentLibrary";
import { OnboardingWizard } from "./components/OnboardingWizard";
import { PlanningTimeline } from "./components/PlanningTimeline";
import { ProposalWorkspace } from "./components/ProposalWorkspace";
import { ProjectCollabChat } from "./components/ProjectCollabChat";
import { ProjectDashboard } from "./components/ProjectDashboard";
import { MeetingsHub } from "./components/MeetingsHub";
import { MyWork } from "./components/MyWork";
import { ProjectSearch } from "./components/ProjectSearch";
import { ProposalSubmissionWorkspace } from "./components/ProposalSubmissionWorkspace";
import { ProjectTodos } from "./components/ProjectTodos";
import { ResearchWorkspace } from "./components/ResearchWorkspace";
import { ResourcesWorkspace } from "./components/ResourcesWorkspace";
import { TeachingCoursesWorkspace } from "./components/TeachingCoursesWorkspace";
import { TeachingWorkspace } from "./components/TeachingWorkspace";
import { NewProjectModal } from "./components/NewProjectModal";
import { ProjectSettingsModal } from "./components/ProjectSettingsModal";
import { UserProfileModal } from "./components/UserProfileModal";
import { api, AUTH_EXPIRED_EVENT, PROJECT_DATA_CHANGED_EVENT } from "./lib/api";
import { currentProjectMonth } from "./lib/utils";
import prainaLogoWhite from "./assets/praina-logo-white.svg";
import { useAutoRefresh } from "./lib/useAutoRefresh";
import type { AppNotification, AuthTokens, MeResponse, Project, ProposalCallBrief, ResearchSpace, UserSuggestion, UserSuggestionCategory } from "./types";

type View = "my-work" | "projects-home" | "research-home" | "teaching-home" | "dashboard" | "call" | "proposal" | "submission" | "delivery" | "workbench" | "meetings" | "project-chat" | "assistant" | "wizard" | "matrix" | "documents" | "planning" | "admin" | "todos" | "search" | "research" | "teaching" | "courses" | "resources" | "bibliography";
type WorkspaceFamily = "projects" | "research" | "teaching";
type ResearchTabState = "references" | "notes" | "paper" | "iterations" | "overview" | "chat" | "files" | "todos";
type ResearchNavigationState = {
  selectedCollectionId: string | null;
  tab: ResearchTabState;
  selectedBibliographyCollectionId: string | null;
};
type AppNavigationSnapshot = {
  view: View;
  workspaceFamily: WorkspaceFamily;
  selectedProjectId: string;
  selectedResearchSpaceId: string;
  research: ResearchNavigationState;
};
type NavItem = { id: View; label: string; icon: typeof faSitemap };
type NavSection = { key: string; label: string; collapsible: boolean; items: NavItem[] };
const ASSISTANT_PENDING_PROMPT_KEY = "assistant_pending_prompt";
const ACTIVE_PROJECT_KEY = "active_project_id";
const ACTIVE_RESEARCH_SPACE_KEY = "active_research_space_id";
const SIDEBAR_COLLAPSED_KEY = "sidebar_collapsed";
const NAV_GROUPS_KEY = "nav_groups_collapsed";
const ACCESS_TOKEN_KEY = "auth_access_token";
const REFRESH_TOKEN_KEY = "auth_refresh_token";
const RESEARCH_ROUTE_FALLBACK_PROJECT_ID = "00000000-0000-0000-0000-000000000000";
const RESEARCH_TOUR_KEY = "research_tour_version";
const RESEARCH_TOUR_VERSION = "2026-04-research-v1";

function normalizeSnapshot(snapshot: AppNavigationSnapshot): string {
  return JSON.stringify(snapshot);
}

const LINK_TYPE_VIEW_MAP: Record<string, View> = {
  deliverable: "delivery",
  risk: "delivery",
  document: "documents",
  meeting: "meetings",
  task: "planning",
  work_package: "planning",
  milestone: "planning",
  action_item: "meetings",
  todo: "todos",
  chat: "assistant",
  inbox: "dashboard",
  research_collection: "research",
  research_reference: "research",
  research_note: "research",
  resource_booking: "resources",
  bibliography_reference: "bibliography",
  project_broadcast: "project-chat",
  project_chat_mention: "project-chat",
  study_chat_mention: "research",
  lab_broadcast: "resources",
};

export default function App() {
  const defaultResearchNavigationState: ResearchNavigationState = {
    selectedCollectionId: null,
    tab: "overview",
    selectedBibliographyCollectionId: null,
  };
  const [workspaceFamily, setWorkspaceFamily] = useState<WorkspaceFamily>("projects");
  const [view, setView] = useState<View>("projects-home");
  const [projects, setProjects] = useState<Project[]>([]);
  const [researchSpaces, setResearchSpaces] = useState<ResearchSpace[]>([]);
  const [authTokens, setAuthTokens] = useState<AuthTokens | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const currentUser = me?.user ?? null;
  const canAccessResearch = currentUser?.can_access_research ?? false;
  const canAccessTeaching = currentUser?.can_access_teaching ?? false;
  const isSuperAdmin = currentUser?.platform_role === "super_admin";
  const isStudent = currentUser?.platform_role === "student";
  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    () => (typeof window !== "undefined" ? window.sessionStorage.getItem(ACTIVE_PROJECT_KEY) || "" : "")
  );
  const [selectedResearchSpaceId, setSelectedResearchSpaceId] = useState<string>(
    () => (typeof window !== "undefined" ? window.sessionStorage.getItem(ACTIVE_RESEARCH_SPACE_KEY) || "" : "")
  );
  const [researchNavigationState, setResearchNavigationState] = useState<ResearchNavigationState>(defaultResearchNavigationState);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(
    () => typeof window !== "undefined" && window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1"
  );
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [collapsedNavGroups, setCollapsedNavGroups] = useState<Record<string, boolean>>(
    () => {
      if (typeof window === "undefined") return {};
      try {
        return JSON.parse(window.localStorage.getItem(NAV_GROUPS_KEY) || "{}") as Record<string, boolean>;
      } catch {
        return {};
      }
    }
  );
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [newResearchSpaceOpen, setNewResearchSpaceOpen] = useState(false);
  const [editingResearchSpaceId, setEditingResearchSpaceId] = useState<string | null>(null);
  const [newResearchSpaceTitle, setNewResearchSpaceTitle] = useState("");
  const [newResearchSpaceFocus, setNewResearchSpaceFocus] = useState("");
  const [newResearchSpaceProjectId, setNewResearchSpaceProjectId] = useState("");
  const [newResearchSpaceError, setNewResearchSpaceError] = useState("");
  const [savingResearchSpace, setSavingResearchSpace] = useState(false);
  const [workspaceBrowserSearch, setWorkspaceBrowserSearch] = useState("");
  const [projectSettingsOpen, setProjectSettingsOpen] = useState(false);
  const [error, setError] = useState("");
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifDropdownOpen, setNotifDropdownOpen] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const notifDropdownRef = useRef<HTMLDivElement>(null);
  const [pendingDocumentKey, setPendingDocumentKey] = useState<string | null>(null);
  const [pendingMeetingId, setPendingMeetingId] = useState<string | null>(null);
  const [pendingProjectChatRoomId, setPendingProjectChatRoomId] = useState<string | null>(null);
  const [pendingBibliographyReferenceId, setPendingBibliographyReferenceId] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [proposalCallBrief, setProposalCallBrief] = useState<ProposalCallBrief | null>(null);
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);
  const [workspaceSwitcherOpen, setWorkspaceSwitcherOpen] = useState(false);
  const [shortcutHudVisible, setShortcutHudVisible] = useState(false);
  const [researchTourOpen, setResearchTourOpen] = useState(false);
  const [researchTourStepIndex, setResearchTourStepIndex] = useState(0);
  const [suggestionPanelOpen, setSuggestionPanelOpen] = useState(false);
  const [suggestionPanelView, setSuggestionPanelView] = useState<"list" | "create">("list");
  const [suggestionContent, setSuggestionContent] = useState("");
  const [suggestionCategory, setSuggestionCategory] = useState<UserSuggestionCategory>("feature");
  const [savingSuggestion, setSavingSuggestion] = useState(false);
  const [mySuggestions, setMySuggestions] = useState<UserSuggestion[]>([]);
  const [mySuggestionsLoading, setMySuggestionsLoading] = useState(false);
  const [suggestionStatusFilter, setSuggestionStatusFilter] = useState<string>("");
  const workspaceBrowserSearchRef = useRef<HTMLInputElement>(null);
  const navigationHistoryRef = useRef<AppNavigationSnapshot[]>([]);
  const restoringNavigationRef = useRef(false);
  const restoreTargetSnapshotRef = useRef<string | null>(null);
  const [navigationHistoryIndex, setNavigationHistoryIndex] = useState(-1);

  const currentNavigationSnapshot = useMemo<AppNavigationSnapshot>(() => ({
    view,
    workspaceFamily,
    selectedProjectId,
    selectedResearchSpaceId,
    research: {
      selectedCollectionId: researchNavigationState.selectedCollectionId,
      tab: researchNavigationState.selectedCollectionId ? researchNavigationState.tab : "overview",
      selectedBibliographyCollectionId: researchNavigationState.selectedBibliographyCollectionId,
    },
  }), [view, workspaceFamily, selectedProjectId, selectedResearchSpaceId, researchNavigationState]);

  const researchTourSteps: GuidedTourStep[] = useMemo(() => ([
    { id: "spaces", target: "research-space-grid", title: "Spaces", text: "Spaces group studies around a broad topic." },
    { id: "studies", target: "research-study-grid", title: "Studies", text: "Studies are the focused units where research work happens." },
    { id: "inbox", target: "study-inbox-tab", title: "Inbox", text: "Use Inbox as the research log." },
    { id: "references", target: "study-references-tab", title: "References", text: "Keep the literature tied to the study here." },
    { id: "paper", target: "study-paper-tab", title: "Paper", text: "Turn logs and references into questions, claims, and structure here." },
    { id: "iterations", target: "study-iterations-tab", title: "Iterations", text: "Review periods of work and turn them into results here." },
  ]), []);
  const currentResearchTourStep = researchTourSteps[researchTourStepIndex] ?? null;

  // Global keyboard shortcuts
  useEffect(() => {
    function isEditableTarget(target: EventTarget | null) {
      const element = target as HTMLElement | null;
      if (!element) return false;
      const tag = element.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || element.isContentEditable;
    }

    function handleGlobalKeyDown(e: KeyboardEvent) {
      if (e.key === "Control" || e.key === "Meta") {
        setShortcutHudVisible(true);
      }
      if ((e.ctrlKey || e.metaKey) && e.code === "Slash") {
        if (isEditableTarget(e.target)) return;
        e.preventDefault();
        setWorkspaceSwitcherOpen(true);
        return;
      }
      // Cmd+K / Ctrl+K → open command palette
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdPaletteOpen((prev) => !prev);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "f") {
        if (view === "projects-home" || view === "research-home" || view === "teaching-home") {
          e.preventDefault();
          workspaceBrowserSearchRef.current?.focus();
          workspaceBrowserSearchRef.current?.select();
          return;
        }
      }
      // Esc → close topmost modal overlay (if not inside an input/textarea)
      if (e.key === "Escape") {
        if (workspaceSwitcherOpen) {
          setWorkspaceSwitcherOpen(false);
          return;
        }
        if (cmdPaletteOpen) {
          setCmdPaletteOpen(false);
          return;
        }
        const overlays = document.querySelectorAll<HTMLElement>(".modal-overlay");
        if (overlays.length > 0) {
          const topmost = overlays[overlays.length - 1];
          topmost.click();
        }
      }
    }
    function handleGlobalKeyUp(e: KeyboardEvent) {
      if (e.key === "Control" || e.key === "Meta") {
        setShortcutHudVisible(false);
      }
    }
    function handleWindowBlur() {
      setShortcutHudVisible(false);
    }
    document.addEventListener("keydown", handleGlobalKeyDown);
    document.addEventListener("keyup", handleGlobalKeyUp);
    window.addEventListener("blur", handleWindowBlur);
    return () => {
      document.removeEventListener("keydown", handleGlobalKeyDown);
      document.removeEventListener("keyup", handleGlobalKeyUp);
      window.removeEventListener("blur", handleWindowBlur);
    };
  }, [cmdPaletteOpen, workspaceSwitcherOpen, view]);

  // Dynamic page title per view
  useEffect(() => {
    const titles: Record<View, string> = {
      "my-work": "My Work",
      "projects-home": "Projects",
      "research-home": "Research",
      "teaching-home": "Teaching",
      dashboard: "Dashboard",
      call: "Call",
      proposal: "Proposal",
      submission: "Submission",
      delivery: "Delivery Board",
      workbench: "Workbench",
      meetings: "Meetings",
      "project-chat": "Chat",
      assistant: "Assistant",
      wizard: "Wizard",
      matrix: "Risk Matrix",
      documents: "Documents",
      planning: "Planning",
      admin: "Admin",
      todos: "Todos",
      search: "Search",
      research: "Research",
      teaching: "Teaching",
      courses: "Courses",
      resources: "Resources",
      bibliography: "Bibliography",
    };
    document.title = `${titles[view] || "Praina"} — Praina`;
  }, [view]);

  async function bootstrapAuthSession() {
    if (typeof window === "undefined") return;
    const accessToken = window.localStorage.getItem(ACCESS_TOKEN_KEY);
    const refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!accessToken || !refreshToken) {
      api.setAuthToken(null);
      setAuthTokens(null);
      setMe(null);
      return;
    }
    try {
      api.setAuthToken(accessToken);
      const meResponse = await api.me();
      setAuthTokens({
        access_token: accessToken,
        refresh_token: refreshToken,
        token_type: "bearer",
        expires_in_seconds: 0,
      });
      setMe(meResponse);
    } catch {
      api.setAuthToken(null);
      window.localStorage.removeItem(ACCESS_TOKEN_KEY);
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
      setAuthTokens(null);
      setMe(null);
    }
  }

  function clearPermalinkSearch() {
    if (typeof window === "undefined") return;
    const nextUrl = `${window.location.pathname}${window.location.hash || ""}`;
    window.history.replaceState({}, "", nextUrl);
  }

  async function loadProjects() {
    try {
      const response = await api.listProjects();
      setProjects(response.items);
      setSelectedProjectId((current) => {
        const exists = response.items.some((project) => project.id === current);
        const resolved = exists ? current : (response.items[0]?.id ?? "");
        if (typeof window !== "undefined") {
          if (resolved) window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, resolved);
          else window.sessionStorage.removeItem(ACTIVE_PROJECT_KEY);
        }
        return resolved;
      });
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects.");
    }
  }

  async function loadResearchSpaces() {
    try {
      const response = await api.listResearchSpaces({ page: 1, page_size: 100 });
      setResearchSpaces(response.items);
      setSelectedResearchSpaceId((current) => {
        const exists = response.items.some((item) => item.id === current);
        const resolved = exists ? current : "";
        if (typeof window !== "undefined") {
          if (resolved) window.sessionStorage.setItem(ACTIVE_RESEARCH_SPACE_KEY, resolved);
          else window.sessionStorage.removeItem(ACTIVE_RESEARCH_SPACE_KEY);
        }
        return resolved;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load research spaces.");
    }
  }

  async function pollUnreadCount() {
    try {
      const res = await api.notificationUnreadCount();
      setUnreadCount(res.count);
    } catch { /* ignore */ }
  }

  async function loadNotifications() {
    try {
      const res = await api.listNotifications(undefined, false, 1, 10);
      setNotifications(res.items);
      setUnreadCount((prev) => {
        const unread = res.items.filter((n) => n.status === "unread").length;
        return Math.max(prev, unread);
      });
    } catch { /* ignore */ }
  }

  async function handleMarkAllRead() {
    await api.markAllNotificationsRead();
    setUnreadCount(0);
    setNotifications((prev) => prev.map((n) => ({ ...n, status: "read" })));
  }

  useEffect(() => {
    void bootstrapAuthSession();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const requestedView = params.get("view");
    const requestedProjectId = params.get("project");
    const requestedPaperId = params.get("paper");
    if (requestedProjectId) {
      setSelectedProjectId(requestedProjectId);
      window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, requestedProjectId);
    }
    if (requestedView === "bibliography") {
      setView("bibliography");
      setWorkspaceFamily("research");
    }
    if (requestedPaperId) {
      setPendingBibliographyReferenceId(requestedPaperId);
    }
  }, []);

  // Poll unread count every 30 seconds
  useEffect(() => {
    if (!me) return;
    void pollUnreadCount();
    const interval = setInterval(() => void pollUnreadCount(), 30_000);
    return () => clearInterval(interval);
  }, [me?.user.id]);

  useEffect(() => {
    if (!me) {
      setProjects([]);
      setResearchSpaces([]);
      setSelectedProjectId("");
      setSelectedResearchSpaceId("");
      setResearchNavigationState(defaultResearchNavigationState);
      navigationHistoryRef.current = [];
      setNavigationHistoryIndex(-1);
      return;
    }
    void loadProjects();
    void loadResearchSpaces();
  }, [me?.user.id]);

  useEffect(() => {
    if (!currentUser) return;
    const snapshot = currentNavigationSnapshot;
    if (restoreTargetSnapshotRef.current) {
      return;
    }
    const currentEntry = navigationHistoryIndex >= 0 ? navigationHistoryRef.current[navigationHistoryIndex] : null;
    if (currentEntry && normalizeSnapshot(currentEntry) === normalizeSnapshot(snapshot)) {
      return;
    }
    const nextHistory = navigationHistoryRef.current.slice(0, navigationHistoryIndex + 1);
    nextHistory.push(snapshot);
    navigationHistoryRef.current = nextHistory;
    setNavigationHistoryIndex(nextHistory.length - 1);
  }, [currentUser, currentNavigationSnapshot, navigationHistoryIndex]);

  useEffect(() => {
    const target = restoreTargetSnapshotRef.current;
    if (!target) return;
    if (normalizeSnapshot(currentNavigationSnapshot) !== target) return;
    restoreTargetSnapshotRef.current = null;
    restoringNavigationRef.current = false;
  }, [currentNavigationSnapshot]);

  function handleAuthenticated(tokens: AuthTokens, meResponse: MeResponse) {
    api.setAuthToken(tokens.access_token);
    setAuthTokens(tokens);
    setMe(meResponse);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
      window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    }
    void loadProjects();
    void loadResearchSpaces();
  }

  function handleLogout() {
    api.setAuthToken(null);
    setAuthTokens(null);
    setMe(null);
    setProjects([]);
    setResearchSpaces([]);
    setSelectedProjectId("");
    setSelectedResearchSpaceId("");
    setError("");
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(ACCESS_TOKEN_KEY);
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
      window.sessionStorage.removeItem(ACTIVE_PROJECT_KEY);
      window.sessionStorage.removeItem(ACTIVE_RESEARCH_SPACE_KEY);
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onAuthExpired = () => {
      handleLogout();
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
  }, []);

  function handleProjectCreated(project: Project) {
    setSelectedProjectId(project.id);
    if (project.project_kind === "teaching") {
      setWorkspaceFamily("teaching");
      setView("teaching");
    } else if (project.project_mode === "proposal") {
      setWorkspaceFamily("projects");
      setView("call");
    } else {
      setWorkspaceFamily("projects");
    }
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, project.id);
    }
    void loadProjects();
  }

  function handleProjectUpdated(project: Project) {
    setSelectedProjectId(project.id);
    setWorkspaceFamily(project.project_kind === "teaching" ? "teaching" : "projects");
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, project.id);
    }
    void loadProjects();
  }

  function handleProjectDeleted(projectId: string) {
    if (selectedProjectId === projectId) {
      setSelectedProjectId("");
      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem(ACTIVE_PROJECT_KEY);
      }
    }
    setProjectSettingsOpen(false);
    setView("dashboard");
    void loadProjects();
  }

  function handleSelectResearchSpace(spaceId: string) {
    setSelectedResearchSpaceId(spaceId);
    const selected = researchSpaces.find((item) => item.id === spaceId) ?? null;
    if (selected?.linked_project_id && projects.some((project) => project.id === selected.linked_project_id)) {
      setSelectedProjectId(selected.linked_project_id);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, selected.linked_project_id);
      }
    }
    if (typeof window !== "undefined") {
      if (spaceId) window.sessionStorage.setItem(ACTIVE_RESEARCH_SPACE_KEY, spaceId);
      else window.sessionStorage.removeItem(ACTIVE_RESEARCH_SPACE_KEY);
    }
  }

  function openResearchSpace(spaceId: string) {
    handleSelectResearchSpace(spaceId);
    setResearchNavigationState({
      selectedCollectionId: null,
      tab: "overview",
      selectedBibliographyCollectionId: null,
    });
    setWorkspaceFamily("research");
    setView("research");
  }

  function applyNavigationSnapshot(snapshot: AppNavigationSnapshot) {
    restoringNavigationRef.current = true;
    restoreTargetSnapshotRef.current = normalizeSnapshot(snapshot);
    setWorkspaceFamily(snapshot.workspaceFamily);
    setView(snapshot.view);
    setSelectedProjectId(snapshot.selectedProjectId);
    setSelectedResearchSpaceId(snapshot.selectedResearchSpaceId);
    setResearchNavigationState(snapshot.research);
    if (typeof window !== "undefined") {
      if (snapshot.selectedProjectId) window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, snapshot.selectedProjectId);
      else window.sessionStorage.removeItem(ACTIVE_PROJECT_KEY);
      if (snapshot.selectedResearchSpaceId) window.sessionStorage.setItem(ACTIVE_RESEARCH_SPACE_KEY, snapshot.selectedResearchSpaceId);
      else window.sessionStorage.removeItem(ACTIVE_RESEARCH_SPACE_KEY);
    }
  }

  function handleNavigateBack() {
    if (navigationHistoryIndex <= 0) return;
    const nextIndex = navigationHistoryIndex - 1;
    const snapshot = navigationHistoryRef.current[nextIndex];
    if (!snapshot) return;
    setNavigationHistoryIndex(nextIndex);
    applyNavigationSnapshot(snapshot);
  }

  function handleNavigateForward() {
    if (navigationHistoryIndex < 0 || navigationHistoryIndex >= navigationHistoryRef.current.length - 1) return;
    const nextIndex = navigationHistoryIndex + 1;
    const snapshot = navigationHistoryRef.current[nextIndex];
    if (!snapshot) return;
    setNavigationHistoryIndex(nextIndex);
    applyNavigationSnapshot(snapshot);
  }

  const handleResearchNavigationStateChange = useCallback((next: ResearchNavigationState) => {
    setResearchNavigationState((prev) => (
      prev.selectedCollectionId === next.selectedCollectionId &&
      prev.tab === next.tab &&
      prev.selectedBibliographyCollectionId === next.selectedBibliographyCollectionId
    ) ? prev : next);
  }, []);

  function handleSelectProject(projectId: string) {
    setSelectedProjectId(projectId);
    const selected = projects.find((project) => project.id === projectId);
    if (selected) {
      if (selected.project_kind === "teaching") {
        setWorkspaceFamily("teaching");
      } else if (workspaceFamily === "teaching") {
        setWorkspaceFamily("projects");
      }
    }
    if (typeof window !== "undefined") {
      if (projectId) window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, projectId);
      else window.sessionStorage.removeItem(ACTIVE_PROJECT_KEY);
    }
  }

  function openProjectSettings(projectId: string) {
    handleSelectProject(projectId);
    setProjectSettingsOpen(true);
  }

  const stableLoadProjects = useCallback(() => { void loadProjects(); }, [me?.user.id]);
  useAutoRefresh(stableLoadProjects);

  function handleNavigate(targetView: View, entityId?: string) {
    if (targetView === "documents" && entityId) {
      setPendingDocumentKey(entityId);
    } else if (targetView === "meetings" && entityId) {
      setPendingMeetingId(entityId);
    } else if (targetView === "project-chat" && entityId) {
      setPendingProjectChatRoomId(entityId);
    }
    let targetFamily = workspaceFamily;
    if (targetView === "courses" || targetView === "teaching" || targetView === "teaching-home") targetFamily = "teaching";
    else if (targetView === "research" || targetView === "research-home" || targetView === "bibliography") targetFamily = "research";
    else if (["projects-home", "dashboard", "call", "proposal", "submission", "delivery", "workbench", "wizard", "matrix", "planning", "documents"].includes(targetView)) {
      targetFamily = "projects";
    }
    if (targetFamily !== "research" && targetView !== "courses" && targetView !== "resources" && targetView !== "bibliography" && targetView !== "teaching-home" && targetView !== "projects-home") {
      const sectionProjects = projects.filter((project) =>
        targetFamily === "teaching" ? project.project_kind === "teaching" : project.project_kind !== "teaching"
      );
      const selected = projects.find((project) => project.id === selectedProjectId) ?? null;
      const selectedMatchesSection = selected
        ? (targetFamily === "teaching" ? selected.project_kind === "teaching" : selected.project_kind !== "teaching")
        : false;
      if (!selectedMatchesSection && sectionProjects.length > 0) {
        handleSelectProject(sectionProjects[0].id);
      }
    }
    if (targetView === "research") {
      handleSelectResearchSpace("");
      if (entityId) {
        setResearchNavigationState({
          selectedCollectionId: entityId,
          tab: "chat",
          selectedBibliographyCollectionId: null,
        });
      }
    }
    setWorkspaceFamily(targetFamily);
    setView(targetView);
    setMobileSidebarOpen(false);
  }

  function openAssistantWithPrompt(prompt: string) {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(ASSISTANT_PENDING_PROMPT_KEY, prompt);
    }
    handleNavigate("assistant");
  }

  function toggleSidebar() {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
      }
      return next;
    });
  }

  function toggleNavGroup(key: string) {
    setCollapsedNavGroups((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      if (typeof window !== "undefined") {
        window.localStorage.setItem(NAV_GROUPS_KEY, JSON.stringify(next));
      }
      return next;
    });
  }

  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (notifDropdownRef.current && !notifDropdownRef.current.contains(event.target as Node)) {
        setNotifDropdownOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (notifDropdownOpen || userMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [notifDropdownOpen, userMenuOpen]);

  const activeProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const activeResearchSpace = researchSpaces.find((item) => item.id === selectedResearchSpaceId) ?? null;
  const researchLinkedProject =
    projects.find((project) => project.id === activeResearchSpace?.linked_project_id) ?? null;
  const effectiveResearchProjectId = researchLinkedProject?.id || RESEARCH_ROUTE_FALLBACK_PROJECT_ID;

  useEffect(() => {
    if (view === "courses" || view === "teaching") setWorkspaceFamily("teaching");
    else if (view === "teaching-home") setWorkspaceFamily("teaching");
    else if (view === "research" || view === "research-home" || view === "bibliography") setWorkspaceFamily("research");
    else if (view === "projects-home" || ["dashboard", "call", "proposal", "submission", "delivery", "workbench", "wizard", "matrix", "planning", "documents"].includes(view)) setWorkspaceFamily("projects");
  }, [view]);

  useEffect(() => {
    if (restoreTargetSnapshotRef.current) return;
    if (workspaceFamily !== "research") return;
    if (
      activeResearchSpace?.linked_project_id &&
      (!selectedProjectId || selectedProjectId === RESEARCH_ROUTE_FALLBACK_PROJECT_ID)
    ) {
      setSelectedProjectId(activeResearchSpace.linked_project_id);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, activeResearchSpace.linked_project_id);
      }
    }
  }, [workspaceFamily, activeResearchSpace?.linked_project_id, selectedProjectId]);

  useEffect(() => {
    function handleProjectDataChanged(event: Event) {
      const detail = (event as CustomEvent<{ projectId?: string }>).detail;
      if (!detail?.projectId || detail.projectId !== selectedProjectId) return;
      void loadProjects();
      if (activeProject?.project_mode === "proposal") {
        api.getProposalCallBrief(detail.projectId)
          .then((res) => setProposalCallBrief(res))
          .catch(() => setProposalCallBrief(null));
      }
    }
    window.addEventListener(PROJECT_DATA_CHANGED_EVENT, handleProjectDataChanged as EventListener);
    return () => window.removeEventListener(PROJECT_DATA_CHANGED_EVENT, handleProjectDataChanged as EventListener);
  }, [selectedProjectId, activeProject?.project_mode]);

  useEffect(() => {
    if (workspaceFamily !== "projects" || !selectedProjectId || activeProject?.project_mode !== "proposal") {
      setProposalCallBrief(null);
      return;
    }
    api.getProposalCallBrief(selectedProjectId)
      .then((res) => setProposalCallBrief(res))
      .catch(() => setProposalCallBrief(null));
  }, [selectedProjectId, activeProject?.project_mode, workspaceFamily]);

  // Redirect to dashboard if on an execution-only view while in proposal mode
  useEffect(() => {
    if (workspaceFamily === "projects" && activeProject?.project_mode === "proposal") {
      const proposalViews = new Set<View>(["my-work", "projects-home", "courses", "dashboard", "call", "proposal", "submission", "project-chat", "assistant", "wizard", "resources", "bibliography", "admin"]);
      if (!proposalViews.has(view)) {
        setView("dashboard");
      }
    }
  }, [activeProject?.project_mode, view, workspaceFamily]);

  useEffect(() => {
    if (workspaceFamily === "teaching" && activeProject?.project_kind === "teaching") {
      const teachingViews = new Set<View>(["my-work", "teaching-home", "courses", "teaching", "project-chat", "assistant", "todos", "search", "resources", "bibliography", "admin"]);
      if (!teachingViews.has(view)) {
        setView("courses");
      }
    }
  }, [activeProject?.project_kind, view, workspaceFamily]);

  const viewTitle: Record<View, string> = {
    "my-work": "My Work",
    "projects-home": "Projects",
    "research-home": "Research",
    "teaching-home": "Teaching",
    dashboard: "Dashboard",
    call: "Call",
    proposal: "Proposal",
    submission: "Submission",
    delivery: "Delivery",
    workbench: "Workbench",
    meetings: "Meetings",
    "project-chat": "Chat",
    assistant: "Assistant",
    wizard: "Setup",
    matrix: "Assignments",
    documents: "Documents",
    planning: "Timeline",
    todos: "Todos",
    search: "Search",
    bibliography: "Bibliography",
    research: "Research",
    teaching: "Teaching",
    courses: "Courses",
    resources: "Resources",
    admin: "Admin",
  };

  const ALWAYS_VISIBLE_VIEWS = new Set<View>(["my-work"]);
  const PROPOSAL_MODE_VIEWS = new Set<View>(["dashboard", "call", "proposal", "submission", "project-chat", "assistant", "wizard", "search", "resources", "admin"]);
  const TEACHING_MODE_VIEWS = new Set<View>(["courses", "teaching", "project-chat", "assistant", "todos", "search", "resources", "admin"]);
  const EXECUTION_MODE_HIDDEN = new Set<View>(["proposal"]);
  const researchNavItems: NavItem[] = [
    { id: "projects-home", label: "Projects", icon: faSitemap },
    { id: "dashboard", label: "Dashboard", icon: faChartLine },
    { id: "call", label: "Call", icon: faLayerGroup },
    { id: "proposal", label: "Proposal", icon: faFileLines },
    { id: "submission", label: "Submission", icon: faSquareCheck },
    { id: "delivery", label: "Delivery", icon: faClipboardCheck },
    { id: "workbench", label: "Workbench", icon: faWrench },
    { id: "meetings", label: "Meetings", icon: faCalendarDay },
    { id: "project-chat", label: "Chat", icon: faUsers },
    { id: "assistant", label: "Assistant", icon: faComments },
    { id: "wizard", label: "Setup", icon: faSitemap },
    { id: "matrix", label: "Assignments", icon: faUsers },
    { id: "planning", label: "Timeline", icon: faBarsStaggered },
    { id: "documents", label: "Documents", icon: faBook },
    { id: "todos", label: "Todos", icon: faSquareCheck },
    { id: "research", label: "Research", icon: faFlask },
    { id: "search", label: "Search", icon: faSearch },
  ];
  const teachingNavItems: NavItem[] = [
    { id: "teaching-home", label: "Teaching", icon: faGraduationCap },
    { id: "courses", label: "Courses", icon: faBook },
    { id: "teaching", label: "Projects", icon: faGraduationCap },
    { id: "project-chat", label: "Chat", icon: faUsers },
    { id: "assistant", label: "Assistant", icon: faComments },
    { id: "todos", label: "Todos", icon: faSquareCheck },
    { id: "search", label: "Search", icon: faSearch },
  ];
  const sharedNavItems: NavItem[] = isStudent ? [] : [
    { id: "bibliography", label: "Bibliography", icon: faBook },
  ];
  const platformNavItems: NavItem[] = isStudent ? [] : [
    { id: "resources", label: "Resources", icon: faWrench },
  ];

  const isProposalMode = activeProject?.project_mode === "proposal";
  const isTeachingProject = activeProject?.project_kind === "teaching";
  const visibleProjects = projects.filter((project) =>
    workspaceFamily === "teaching" ? project.project_kind === "teaching" : project.project_kind !== "teaching"
  );
  const visibleResearchProjects = projects.filter((project) => project.project_kind !== "teaching");
  const proposalCallReady = Boolean(proposalCallBrief?.source_call_id || proposalCallBrief?.call_title?.trim());
  const navSections: NavSection[] =
    workspaceFamily === "teaching"
      ? canAccessTeaching
        ? [
            {
              key: "teaching",
              label: "Teaching",
              collapsible: false,
              items: teachingNavItems.filter((item) => ALWAYS_VISIBLE_VIEWS.has(item.id) || TEACHING_MODE_VIEWS.has(item.id)),
            },
            {
              key: "library",
              label: "Library",
              collapsible: false,
              items: sharedNavItems,
            },
            {
              key: "platform",
              label: "Platform",
              collapsible: false,
              items: platformNavItems,
            },
          ]
        : []
      : workspaceFamily === "research"
        ? canAccessResearch
          ? [
              {
                key: "research-workspace",
                label: "Research",
                collapsible: false,
                items: [
                  { id: "research", label: "Studies", icon: faBook },
                  { id: "research-home", label: "Spaces", icon: faFlask },
                  ...(!isStudent ? [{ id: "assistant" as View, label: "Assistant", icon: faComments }] : []),
                  { id: "search", label: "Search", icon: faSearch },
                ],
              },
              {
                key: "library",
                label: "Library",
                collapsible: false,
                items: sharedNavItems,
              },
              {
                key: "platform",
                label: "Platform",
                collapsible: false,
                items: platformNavItems,
              },
            ]
          : []
        : canAccessResearch
        ? [
            {
              key: "projects-project",
              label: "Projects",
              collapsible: true,
              items: researchNavItems
                .filter((item) => ["dashboard", "call", "proposal", "submission", "wizard"].includes(item.id))
                .filter((item) => ALWAYS_VISIBLE_VIEWS.has(item.id) || (isProposalMode ? PROPOSAL_MODE_VIEWS.has(item.id) : !EXECUTION_MODE_HIDDEN.has(item.id))),
            },
            {
              key: "research-work",
              label: "Work",
              collapsible: true,
              items: researchNavItems
                .filter((item) => ["delivery", "workbench", "planning", "documents", "todos"].includes(item.id))
                .filter((item) => ALWAYS_VISIBLE_VIEWS.has(item.id) || (isProposalMode ? PROPOSAL_MODE_VIEWS.has(item.id) : !EXECUTION_MODE_HIDDEN.has(item.id))),
            },
            {
              key: "research-collaboration",
              label: "Collaboration",
              collapsible: true,
              items: researchNavItems
                .filter((item) => ["meetings", "project-chat", "assistant", "matrix", "search"].includes(item.id))
                .filter((item) => ALWAYS_VISIBLE_VIEWS.has(item.id) || (isProposalMode ? PROPOSAL_MODE_VIEWS.has(item.id) : !EXECUTION_MODE_HIDDEN.has(item.id))),
            },
            {
              key: "library",
              label: "Library",
              collapsible: false,
              items: sharedNavItems,
            },
            {
              key: "platform",
              label: "Platform",
              collapsible: false,
              items: platformNavItems,
            },
          ]
        : [];

  const cmdPaletteItems: CommandItem[] = navSections.flatMap((section) =>
    section.items.map((item) => ({
      id: item.id,
      label: item.label,
      icon: item.icon,
      section: section.label,
    }))
  );
  const workspaceSwitcherItems: CommandItem[] = [
    { id: "projects", label: "Projects", icon: faSitemap },
    { id: "research", label: "Research", icon: faFlask },
    { id: "teaching", label: "Teaching", icon: faGraduationCap },
  ];

  function switchWorkspaceFamily(nextFamily: WorkspaceFamily) {
    if (isStudent && nextFamily === "projects") return;
    if ((nextFamily === "projects" || nextFamily === "research") && !canAccessResearch) {
      return;
    }
    if (nextFamily === "teaching" && !canAccessTeaching) {
      return;
    }
    setWorkspaceFamily(nextFamily);
    if (nextFamily === "teaching") {
      setView("teaching-home");
      return;
    }
    if (nextFamily === "research") {
      setView("research");
      return;
    }
    const projectContext = projects.find((project) => project.project_kind !== "teaching");
    if (activeProject?.project_kind === "teaching" && projectContext) {
      setSelectedProjectId(projectContext.id);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, projectContext.id);
      }
    }
    setView("projects-home");
  }
  function isNavItemDisabled(itemId: View): boolean {
    if (workspaceFamily !== "projects") return false;
    if (!isProposalMode) return false;
    if (!proposalCallReady) return itemId !== "call";
    return false;
  }

  const canCreateProjects = currentUser
    ? (currentUser.platform_role === "super_admin" || currentUser.platform_role === "project_creator") &&
      (workspaceFamily === "teaching" ? canAccessTeaching : workspaceFamily === "projects")
    : false;
  const canCreateResearchSpaces = canAccessResearch && !isStudent;
  const userInitials =
    currentUser?.display_name
      .split(" ")
      .map((part) => part[0]?.toUpperCase() || "")
      .slice(0, 2)
      .join("") || "U";
  const activeProjectMonth = currentProjectMonth(activeProject?.start_date);
  const workspaceBrowserQuery = workspaceBrowserSearch.trim().toLowerCase();
  const showContextLink = !["courses", "resources", "projects-home", "research-home", "teaching-home"].includes(view);
  const contextLabel =
    workspaceFamily === "research"
      ? activeResearchSpace?.title || null
      : activeProject?.title || null;
  const contextMeta =
    workspaceFamily === "research"
      ? researchLinkedProject?.code || null
      : activeProject?.code || null;
  const shortcutHints = useMemo(() => {
    const modifier = navigator.platform.toLowerCase().includes("mac") ? "⌘" : "Ctrl";
    const items: Array<{ key: string; label: string }> = [
      { key: `${modifier}+/`, label: "Switch Workspace" },
      { key: `${modifier}+K`, label: "Command Palette" },
    ];
    if (view === "projects-home" || view === "research-home" || view === "teaching-home") {
      items.push({ key: `${modifier}+F`, label: "Search" });
    }
    if (view === "research-home") {
      items.push({ key: "Enter", label: "Open Space" });
    } else if (view === "projects-home" || view === "teaching-home") {
      items.push({ key: "Enter", label: "Open Project" });
    }
    if (view === "bibliography") {
      items.push({ key: "Enter", label: "Semantic Search" });
    }
    items.push({ key: "Esc", label: "Close" });
    return items;
  }, [view]);

  const browserResearchSpaces = researchSpaces.filter((space) => {
    if (!workspaceBrowserQuery) return true;
    const linkedProject = projects.find((project) => project.id === space.linked_project_id) ?? null;
    return [space.title, space.focus || "", linkedProject?.title || "", linkedProject?.code || ""]
      .some((value) => value.toLowerCase().includes(workspaceBrowserQuery));
  });

  const browserResearchProjects = projects
    .filter((project) => project.project_kind !== "teaching")
    .filter((project) =>
      !workspaceBrowserQuery ||
      [project.code, project.title, project.status, project.project_kind].some((value) => value.toLowerCase().includes(workspaceBrowserQuery))
    );

  const browserTeachingProjects = projects
    .filter((project) => project.project_kind === "teaching")
    .filter((project) =>
      !workspaceBrowserQuery ||
      [project.code, project.title, project.status].some((value) => value.toLowerCase().includes(workspaceBrowserQuery))
    );

  useEffect(() => {
    if (!currentUser) return;
    if (isStudent && workspaceFamily === "projects") {
      setWorkspaceFamily("research");
      setView("research");
      return;
    }
    if ((workspaceFamily === "projects" || workspaceFamily === "research") && !canAccessResearch && canAccessTeaching) {
      setWorkspaceFamily("teaching");
      setView("courses");
      return;
    }
    if (workspaceFamily === "teaching" && !canAccessTeaching && canAccessResearch) {
      setWorkspaceFamily("projects");
      setView("dashboard");
    }
  }, [currentUser?.id, workspaceFamily, canAccessResearch, canAccessTeaching, isStudent]);

  useEffect(() => {
    if (!canAccessResearch || researchTourOpen) return;
    if (workspaceFamily !== "research") return;
    if (researchSpaces.length === 0) return;
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(RESEARCH_TOUR_KEY);
    if (stored === RESEARCH_TOUR_VERSION) return;
    setResearchTourStepIndex(0);
    setResearchTourOpen(true);
  }, [canAccessResearch, workspaceFamily, researchSpaces.length, researchTourOpen]);

  useEffect(() => {
    if (!researchTourOpen || !currentResearchTourStep) return;
    if (workspaceFamily !== "research") {
      switchWorkspaceFamily("research");
      return;
    }
    if (currentResearchTourStep.target === "research-space-grid") {
      if (view !== "research-home") setView("research-home");
      return;
    }
    if (!selectedResearchSpaceId && researchSpaces[0]) {
      handleSelectResearchSpace(researchSpaces[0].id);
    }
    if (view !== "research") setView("research");
  }, [
    researchTourOpen,
    currentResearchTourStep,
    workspaceFamily,
    view,
    selectedResearchSpaceId,
    researchSpaces,
  ]);

  function startResearchTour() {
    if (!canAccessResearch) return;
    setResearchTourStepIndex(0);
    setResearchTourOpen(true);
    if (workspaceFamily !== "research") {
      switchWorkspaceFamily("research");
    } else {
      setView("research-home");
    }
  }

  function completeResearchTour() {
    setResearchTourOpen(false);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RESEARCH_TOUR_KEY, RESEARCH_TOUR_VERSION);
    }
  }

  async function loadMySuggestions(statusFilter?: string) {
    try {
      setMySuggestionsLoading(true);
      const res = await api.listMySuggestions({ status: statusFilter || undefined });
      setMySuggestions(res.items);
    } catch {
      // silent
    } finally {
      setMySuggestionsLoading(false);
    }
  }

  async function handleCreateSuggestion() {
    if (!suggestionContent.trim()) return;
    try {
      setSavingSuggestion(true);
      setError("");
      await api.createMySuggestion({ content: suggestionContent.trim(), category: suggestionCategory });
      setSuggestionContent("");
      setSuggestionCategory("feature");
      setSuggestionPanelView("list");
      toast.success("Suggestion sent.");
      void loadMySuggestions(suggestionStatusFilter);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send suggestion.");
    } finally {
      setSavingSuggestion(false);
    }
  }

  if (!currentUser || !authTokens) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />;
  }

  function openNewResearchSpaceModal() {
    setEditingResearchSpaceId(null);
    setNewResearchSpaceTitle("");
    setNewResearchSpaceFocus("");
    setNewResearchSpaceProjectId(selectedProjectId && visibleResearchProjects.some((project) => project.id === selectedProjectId) ? selectedProjectId : "");
    setNewResearchSpaceError("");
    setNewResearchSpaceOpen(true);
  }

  function openEditResearchSpaceModal(space: ResearchSpace) {
    setEditingResearchSpaceId(space.id);
    setNewResearchSpaceTitle(space.title);
    setNewResearchSpaceFocus(space.focus || "");
    setNewResearchSpaceProjectId(space.linked_project_id || "");
    setNewResearchSpaceError("");
    setNewResearchSpaceOpen(true);
  }

  async function handleSaveResearchSpace() {
    if (!newResearchSpaceTitle.trim()) {
      setNewResearchSpaceError("Title is required.");
      return;
    }
    try {
      setSavingResearchSpace(true);
      setNewResearchSpaceError("");
      const payload = {
        title: newResearchSpaceTitle.trim(),
        focus: newResearchSpaceFocus.trim() || null,
        linked_project_id: newResearchSpaceProjectId || null,
      };
      const saved = editingResearchSpaceId
        ? await api.updateResearchSpace(editingResearchSpaceId, payload)
        : await api.createResearchSpace(payload);
      setResearchSpaces((prev) =>
        editingResearchSpaceId ? prev.map((space) => (space.id === saved.id ? saved : space)) : [saved, ...prev]
      );
      openResearchSpace(saved.id);
      setEditingResearchSpaceId(null);
      setNewResearchSpaceTitle("");
      setNewResearchSpaceFocus("");
      setNewResearchSpaceProjectId("");
      setNewResearchSpaceOpen(false);
    } catch (err) {
      setNewResearchSpaceError(err instanceof Error ? err.message : `Failed to ${editingResearchSpaceId ? "update" : "create"} research space.`);
    } finally {
      setSavingResearchSpace(false);
    }
  }

  function renderWorkspaceBrowser() {
    const isResearchBrowser = view === "research-home";
    const isTeachingBrowser = view === "teaching-home";
    const itemCount = isResearchBrowser ? browserResearchSpaces.length : isTeachingBrowser ? browserTeachingProjects.length : browserResearchProjects.length;
    const openProjectFromBrowser = (projectId: string) => {
      handleSelectProject(projectId);
      setView(isTeachingBrowser ? "teaching" : "dashboard");
    };

    return (
      <div className="workspace-browser-page">
        <div className="setup-summary-bar">
          <div className="setup-summary-stats">
            <span>{itemCount} items</span>
          </div>
          <div className="workspace-browser-summary-actions">
            <div className="topbar-project-search workspace-browser-search">
              <FontAwesomeIcon icon={faSearch} />
              <input
                ref={workspaceBrowserSearchRef}
                type="text"
                value={workspaceBrowserSearch}
                onChange={(event) => setWorkspaceBrowserSearch(event.target.value)}
                placeholder={isResearchBrowser ? "Search spaces" : isTeachingBrowser ? "Search teaching projects" : "Search projects"}
              />
            </div>
            {isResearchBrowser && canCreateResearchSpaces ? (
              <button
                type="button"
                className="meetings-new-btn"
                onClick={openNewResearchSpaceModal}
              >
                + New Space
              </button>
            ) : null}
            {!isResearchBrowser && canCreateProjects ? (
              <button type="button" className="meetings-new-btn" onClick={() => setNewProjectOpen(true)}>
                + New Project
              </button>
            ) : null}
          </div>
        </div>
        {itemCount === 0 ? (
          <div className="empty-state-card">
            <strong>{isResearchBrowser ? "No spaces." : "No projects."}</strong>
          </div>
        ) : (
          <div className="workspace-browser-grid" data-tour-id={isResearchBrowser ? "research-space-grid" : undefined}>
            {isResearchBrowser
              ? browserResearchSpaces.map((space) => {
                  const linkedProject = projects.find((project) => project.id === space.linked_project_id) ?? null;
                  const openSpace = () => openResearchSpace(space.id);
                  return (
                    <div
                      key={space.id}
                      className="workspace-browser-card research-space"
                      role="button"
                      tabIndex={0}
                      aria-label={`Open ${space.title}`}
                      onClick={openSpace}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openSpace();
                        } else if (event.key.toLowerCase() === "e") {
                          event.preventDefault();
                          openEditResearchSpaceModal(space);
                        }
                      }}
                    >
                      <div className="workspace-browser-card-accent" />
                      <div className="workspace-browser-card-top">
                        <span className="workspace-browser-icon">
                          <FontAwesomeIcon icon={faFlask} />
                        </span>
                        <span className="chip small">Space</span>
                        {linkedProject ? <span className="chip small">{linkedProject.code}</span> : <span className="chip small">Unlinked</span>}
                      </div>
                      <div className="workspace-browser-card-body">
                        <div className="workspace-browser-card-title">{space.title || "Untitled Space"}</div>
                        {space.focus ? <p>{space.focus}</p> : <p>{linkedProject?.title || "No linked project"}</p>}
                      </div>
                      <div className="workspace-browser-card-foot">
                        <span className="workspace-browser-meta">{linkedProject?.title || "No linked project"}</span>
                        <div className="workspace-browser-card-actions">
                          <button type="button" className="ghost" tabIndex={-1} onClick={(event) => { event.stopPropagation(); openEditResearchSpaceModal(space); }}>
                            Edit
                          </button>
                          <button
                            type="button"
                            tabIndex={-1}
                            onClick={(event) => {
                              event.stopPropagation();
                              openSpace();
                            }}
                          >
                            Open
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })
              : (isTeachingBrowser ? browserTeachingProjects : browserResearchProjects).map((project) => {
                  const openProject = () => openProjectFromBrowser(project.id);
                  return (
                  <div
                    key={project.id}
                    className={`workspace-browser-card ${isTeachingBrowser ? "teaching-project" : "funded-project"}`}
                    role="button"
                    tabIndex={0}
                    aria-label={`Open ${project.title}`}
                    onClick={openProject}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openProject();
                      } else if (event.key.toLowerCase() === "e") {
                        event.preventDefault();
                        openProjectSettings(project.id);
                      }
                    }}
                  >
                    <div className="workspace-browser-card-accent" />
                    <div className="workspace-browser-card-top">
                      <span className="workspace-browser-icon">
                        <FontAwesomeIcon icon={isTeachingBrowser ? faGraduationCap : faSitemap} />
                      </span>
                      <span className="chip small">{isTeachingBrowser ? "Teaching" : project.project_kind}</span>
                      <span className="chip small">{project.code}</span>
                    </div>
                    <div className="workspace-browser-card-body">
                      <div className="workspace-browser-card-title">{project.title || "Untitled Project"}</div>
                      <p>{project.description || project.status}</p>
                    </div>
                    <div className="workspace-browser-card-foot">
                      <span className="workspace-browser-meta">{project.status}</span>
                      <div className="workspace-browser-card-actions">
                        <button type="button" className="ghost" tabIndex={-1} onClick={(event) => { event.stopPropagation(); openProjectSettings(project.id); }}>
                          Edit
                        </button>
                        <button
                          type="button"
                          tabIndex={-1}
                          onClick={(event) => {
                            event.stopPropagation();
                            openProject();
                          }}
                        >
                          Open
                        </button>
                      </div>
                    </div>
                  </div>
                );})}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={`app-frame ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      {mobileSidebarOpen ? <div className="mobile-overlay" onClick={() => setMobileSidebarOpen(false)} /> : null}
      <aside className={`app-sidebar ${mobileSidebarOpen ? "mobile-open" : ""}`}>
        <div className="sidebar-header">
          <button type="button" className="icon-button" onClick={toggleSidebar} aria-label="Toggle sidebar">
            {sidebarCollapsed ? (
              <img src={prainaLogoWhite} alt="Praina" style={{ height: 18, width: 'auto' }} />
            ) : (
              <FontAwesomeIcon icon={faChevronLeft} />
            )}
          </button>
          <div className="brand-block sidebar-expanded-only">
            <img src={prainaLogoWhite} alt="Praina" className="brand-logo" />
            <span className="brand-wordmark">Praina</span>
          </div>
          <button type="button" className="mobile-close-btn" onClick={() => setMobileSidebarOpen(false)} aria-label="Close menu">
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>

        <div className="sidebar-workspace-switch">
          {canAccessResearch && !isStudent ? (
            <button
              type="button"
              className={`sidebar-workspace-btn ${workspaceFamily === "projects" ? "active" : ""}`}
              onClick={() => switchWorkspaceFamily("projects")}
              title={sidebarCollapsed ? "Projects" : undefined}
            >
              <FontAwesomeIcon icon={faSitemap} />
              <span className="sidebar-expanded-only">Projects</span>
            </button>
          ) : null}
          {canAccessResearch ? (
            <button
              type="button"
              className={`sidebar-workspace-btn ${workspaceFamily === "research" ? "active" : ""}`}
              onClick={() => switchWorkspaceFamily("research")}
              title={sidebarCollapsed ? "Research" : undefined}
            >
              <FontAwesomeIcon icon={faFlask} />
              <span className="sidebar-expanded-only">Research</span>
            </button>
          ) : null}
          {canAccessTeaching ? (
            <button
              type="button"
              className={`sidebar-workspace-btn ${workspaceFamily === "teaching" ? "active" : ""}`}
              onClick={() => switchWorkspaceFamily("teaching")}
              title={sidebarCollapsed ? "Teaching" : undefined}
            >
              <FontAwesomeIcon icon={faGraduationCap} />
              <span className="sidebar-expanded-only">Teaching</span>
            </button>
          ) : null}
        </div>

        <nav className="app-nav">
          {navSections.map((section) => (
            <div key={section.label} className="app-nav-section">
              {section.collapsible ? (
                <button
                  type="button"
                  className={`app-nav-section-toggle sidebar-expanded-only ${collapsedNavGroups[section.key] ? "collapsed" : ""}`}
                  onClick={() => toggleNavGroup(section.key)}
                >
                  <span>{section.label}</span>
                  <FontAwesomeIcon icon={faChevronDown} />
                </button>
              ) : (
                <div className="app-nav-section-label sidebar-expanded-only">{section.label}</div>
              )}
              {(sidebarCollapsed || !section.collapsible || !collapsedNavGroups[section.key]) ? section.items.map((item) => {
                const active = view === item.id;
                const disabled = isNavItemDisabled(item.id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`app-nav-item ${active ? "active" : ""} ${disabled ? "disabled" : ""}`}
                    onClick={() => !disabled && handleNavigate(item.id)}
                    title={sidebarCollapsed ? item.label : undefined}
                    disabled={disabled}
                  >
                    <span className="app-nav-icon">
                      <FontAwesomeIcon icon={item.icon} />
                    </span>
                    <span className="app-nav-label sidebar-expanded-only">{item.label}</span>
                  </button>
                );
              }) : null}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button
            type="button"
            className={`sidebar-suggestion-btn ${sidebarCollapsed ? "collapsed" : ""}`}
            onClick={() => { setSuggestionPanelOpen(true); setSuggestionPanelView("list"); void loadMySuggestions(suggestionStatusFilter); }}
            title={sidebarCollapsed ? "Suggestions" : undefined}
          >
            <FontAwesomeIcon icon={faLightbulb} />
            <span className="sidebar-expanded-only">Suggestions</span>
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <button type="button" className="mobile-menu-btn" onClick={() => setMobileSidebarOpen(true)}>
              <FontAwesomeIcon icon={faBars} />
            </button>
            <div className="topbar-history-controls">
              <button
                type="button"
                className="ghost icon-only"
                title="Back"
                onClick={handleNavigateBack}
                disabled={navigationHistoryIndex <= 0}
              >
                <FontAwesomeIcon icon={faChevronLeft} />
              </button>
              <button
                type="button"
                className="ghost icon-only"
                title="Forward"
                onClick={handleNavigateForward}
                disabled={navigationHistoryIndex < 0 || navigationHistoryIndex >= navigationHistoryRef.current.length - 1}
              >
                <FontAwesomeIcon icon={faChevronRight} />
              </button>
            </div>
            <h2>{viewTitle[view]}</h2>
            {showContextLink && contextLabel ? (
              <button
                type="button"
                className={`topbar-context-link ${workspaceFamily}`}
                onClick={() => setView(workspaceFamily === "research" ? "research-home" : workspaceFamily === "teaching" ? "teaching-home" : "projects-home")}
              >
                <strong>{contextLabel}</strong>
                {contextMeta ? <span>{contextMeta}</span> : null}
              </button>
            ) : null}
          </div>

          <div className="topbar-right">
            {workspaceFamily === "research" ? (
              <button
                type="button"
                className="topbar-tour-btn"
                onClick={startResearchTour}
              >
                Tour
              </button>
            ) : null}
            <div className="notif-dropdown-wrapper" ref={notifDropdownRef}>
              <button
                type="button"
                className="ghost icon-only notif-bell"
                title="Notifications"
                onClick={() => {
                  setNotifDropdownOpen((prev) => !prev);
                  if (!notifDropdownOpen) void loadNotifications();
                }}
              >
                <FontAwesomeIcon icon={faBell} />
                {unreadCount > 0 ? <span className="notif-badge">{unreadCount > 99 ? "99+" : unreadCount}</span> : null}
              </button>
              {notifDropdownOpen ? (
                <div className="notif-dropdown">
                  <div className="notif-dropdown-header">
                    <strong>Notifications</strong>
                    {unreadCount > 0 ? (
                      <button type="button" className="ghost small" onClick={() => void handleMarkAllRead()}>Mark all read</button>
                    ) : null}
                  </div>
                  {notifications.length === 0 ? (
                    <div className="notif-empty">No notifications</div>
                  ) : (
                    <div className="notif-list">
                      {notifications.map((n) => (
                        <button
                          key={n.id}
                          type="button"
                          className={`notif-item ${n.status === "unread" ? "unread" : ""}`}
                          onClick={() => {
                            if (n.project_id) {
                              handleSelectProject(n.project_id);
                            }
                            const targetView = n.link_type ? LINK_TYPE_VIEW_MAP[n.link_type] : undefined;
                            if (targetView) {
                              handleNavigate(targetView, n.link_id ?? undefined);
                            }
                            if (n.status === "unread") {
                              void api.markNotificationRead(n.id);
                              setNotifications((prev) => prev.map((item) => item.id === n.id ? { ...item, status: "read" } : item));
                              setUnreadCount((prev) => Math.max(0, prev - 1));
                            }
                            setNotifDropdownOpen(false);
                          }}
                        >
                          <div className="notif-item-title">{n.title}</div>
                          {n.body ? <div className="notif-item-body">{n.body}</div> : null}
                          <div className="notif-item-time">{new Date(n.created_at).toLocaleString()}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
            {isSuperAdmin ? (
              <button
                type="button"
                className="ghost icon-only"
                title="Admin Tools"
                onClick={() => setView("admin")}
              >
                <FontAwesomeIcon icon={faUserShield} />
              </button>
            ) : null}
            <div className="user-menu-wrapper" ref={userMenuRef}>
              <button type="button" className="user-badge" title={currentUser.display_name} onClick={() => setUserMenuOpen((prev) => !prev)}>
                {currentUser.avatar_url ? (
                  <img src={`${import.meta.env.VITE_API_BASE || ""}${currentUser.avatar_url}`} alt={currentUser.display_name} />
                ) : (
                  userInitials
                )}
              </button>
              {userMenuOpen ? (
                <div className="user-menu">
                  <button type="button" onClick={() => { setProfileOpen(true); setUserMenuOpen(false); }}>
                    <FontAwesomeIcon icon={faPen} /> Edit Profile
                  </button>
                  <button type="button" onClick={() => { setView("my-work"); setUserMenuOpen(false); }}>
                    <FontAwesomeIcon icon={faClipboardCheck} /> My Work
                  </button>
                  <button type="button" className="danger" onClick={() => { handleLogout(); setUserMenuOpen(false); }}>
                    <FontAwesomeIcon icon={faRightFromBracket} /> Logout
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {error ? <p className="error top-error">{error}</p> : null}

        <main className="page-content">
          <div className="view-transition" key={view}>
          {view === "my-work" ? <MyWork /> : null}
          {view === "projects-home" ? renderWorkspaceBrowser() : null}
          {view === "research-home" ? renderWorkspaceBrowser() : null}
          {view === "teaching-home" ? renderWorkspaceBrowser() : null}
          {view === "dashboard" ? (
            <ProjectDashboard
              selectedProjectId={selectedProjectId}
              project={activeProject}
              onNavigate={(nextView) => setView(nextView as View)}
              onProjectUpdated={handleProjectUpdated}
            />
          ) : null}
          {view === "call" ? (
            <ProposalWorkspace
              selectedProjectId={selectedProjectId}
              project={activeProject}
              currentUser={currentUser}
              onProjectUpdated={handleProjectUpdated}
              onNavigateToAssistant={() => setView("assistant")}
              onNavigateToCall={() => setView("call")}
              onNavigateToProposal={() => setView("proposal")}
              workspaceMode="call"
            />
          ) : null}
          {view === "proposal" ? (
            <ProposalWorkspace
              selectedProjectId={selectedProjectId}
              project={activeProject}
              currentUser={currentUser}
              onProjectUpdated={handleProjectUpdated}
              onNavigateToAssistant={() => setView("assistant")}
              onNavigateToCall={() => setView("call")}
              onNavigateToProposal={() => setView("proposal")}
              workspaceMode="proposal"
            />
          ) : null}
          {view === "submission" ? (
            <ProposalSubmissionWorkspace
              selectedProjectId={selectedProjectId}
              callBrief={proposalCallBrief}
              currentUser={currentUser}
              project={activeProject}
            />
          ) : null}
          {view === "delivery" ? <DeliveryBoard selectedProjectId={selectedProjectId} project={activeProject} /> : null}
          {view === "workbench" ? <DeliverableWorkbench selectedProjectId={selectedProjectId} onOpenAssistant={openAssistantWithPrompt} /> : null}
          {view === "meetings" ? <MeetingsHub selectedProjectId={selectedProjectId} onOpenAssistant={openAssistantWithPrompt} highlightMeetingId={pendingMeetingId} onHighlightConsumed={() => setPendingMeetingId(null)} /> : null}
          {view === "project-chat" ? (
            <ProjectCollabChat
              key={selectedProjectId}
              selectedProjectId={selectedProjectId}
              currentUser={currentUser}
              accessToken={authTokens.access_token}
              openRoomId={pendingProjectChatRoomId}
              onOpenRoomConsumed={() => setPendingProjectChatRoomId(null)}
            />
          ) : null}
          {view === "assistant" ? (
            <ChatWorkspace
              selectedProjectId={selectedProjectId}
              project={activeProject}
              currentUser={currentUser}
              onNavigate={(v, id) => handleNavigate(v as View, id)}
            />
          ) : null}
          {view === "wizard" ? (
            <OnboardingWizard
              projects={projects}
              selectedProjectId={selectedProjectId}
              canCreateProjects={canCreateProjects}
              onProjectCreated={handleProjectCreated}
              onProjectUpdated={handleProjectUpdated}
            />
          ) : null}
          {view === "matrix" ? <AssignmentMatrix selectedProjectId={selectedProjectId} /> : null}
          {view === "planning" ? <PlanningTimeline selectedProjectId={selectedProjectId} project={activeProject} onNavigate={() => setView("wizard")} /> : null}
          {view === "documents" ? <DocumentLibrary selectedProjectId={selectedProjectId} highlightDocumentKey={pendingDocumentKey} onHighlightConsumed={() => setPendingDocumentKey(null)} /> : null}
          {view === "todos" ? <ProjectTodos selectedProjectId={selectedProjectId} /> : null}
          {view === "research" ? (
            <ResearchWorkspace
              selectedProjectId={effectiveResearchProjectId}
              currentUser={currentUser}
              accessToken={authTokens.access_token}
              currentProject={activeResearchSpace ? (researchLinkedProject ?? null) : null}
              researchSpaceId={activeResearchSpace?.id || ""}
              availableResearchSpaces={researchSpaces}
              onClearResearchSpaceFilter={() => handleSelectResearchSpace("")}
              navigationState={researchNavigationState}
              onNavigationStateChange={handleResearchNavigationStateChange}
              isAdmin={isSuperAdmin}
              isStudent={isStudent}
              researchTourActive={researchTourOpen}
              researchTourStepId={currentResearchTourStep?.target || null}
            />
          ) : null}
          {view === "bibliography" ? (
            <ResearchWorkspace
              selectedProjectId={activeResearchSpace ? effectiveResearchProjectId : (selectedProjectId || RESEARCH_ROUTE_FALLBACK_PROJECT_ID)}
              currentUser={currentUser}
              accessToken={authTokens.access_token}
              currentProject={activeResearchSpace ? (researchLinkedProject ?? null) : activeProject}
              researchSpaceId={activeResearchSpace?.id || ""}
              availableResearchSpaces={researchSpaces}
              onClearResearchSpaceFilter={() => handleSelectResearchSpace("")}
              navigationState={researchNavigationState}
              onNavigationStateChange={handleResearchNavigationStateChange}
              bibliographyOnly
              isAdmin={isSuperAdmin}
              isStudent={isStudent}
              openBibliographyReferenceId={pendingBibliographyReferenceId}
              onOpenBibliographyReferenceConsumed={() => {
                setPendingBibliographyReferenceId(null);
                clearPermalinkSearch();
              }}
              researchTourActive={researchTourOpen}
              researchTourStepId={currentResearchTourStep?.target || null}
            />
          ) : null}
          {view === "resources" ? (
            <ResourcesWorkspace
              currentUser={currentUser}
              onOpenProject={(projectId) => {
                handleSelectProject(projectId);
                const nextProject = projects.find((item) => item.id === projectId);
                if (nextProject?.project_kind === "teaching") setView("teaching");
                else setView("dashboard");
              }}
            />
          ) : null}
          {view === "courses" ? <TeachingCoursesWorkspace currentUser={currentUser} onOpenProject={(projectId) => { handleSelectProject(projectId); setView("teaching"); }} /> : null}
          {view === "teaching" ? (
            <TeachingWorkspace
              selectedProjectId={selectedProjectId}
              project={activeProject}
              currentUser={currentUser}
              onOpenAssistant={openAssistantWithPrompt}
            />
          ) : null}
          {view === "search" ? <ProjectSearch selectedProjectId={selectedProjectId} onNavigate={(v, id) => handleNavigate(v as View, id)} /> : null}
          {view === "admin" ? <AdminPanel selectedProjectId={selectedProjectId} currentUser={currentUser} /> : null}
          </div>
        </main>
      </div>
      <ProjectSettingsModal
        open={projectSettingsOpen}
        project={activeProject}
        currentUser={currentUser}
        onClose={() => setProjectSettingsOpen(false)}
        onProjectUpdated={handleProjectUpdated}
        onProjectDeleted={handleProjectDeleted}
      />
      <NewProjectModal
        open={newProjectOpen}
        platformSection={workspaceFamily === "teaching" ? "teaching" : "research"}
        onClose={() => setNewProjectOpen(false)}
        onProjectCreated={handleProjectCreated}
      />
      {newResearchSpaceOpen ? (
        <div className="modal-overlay" onClick={() => !savingResearchSpace && setNewResearchSpaceOpen(false)}>
          <div className="modal-card research-space-modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <h3>{editingResearchSpaceId ? "Edit Space" : "New Space"}</h3>
            </div>
            <div className="research-space-form">
              <label>
                <span>Title</span>
                <input value={newResearchSpaceTitle} onChange={(event) => setNewResearchSpaceTitle(event.target.value)} placeholder="Adaptive streaming" />
              </label>
              <label>
                <span>Focus</span>
                <textarea value={newResearchSpaceFocus} onChange={(event) => setNewResearchSpaceFocus(event.target.value)} rows={4} />
              </label>
              <label>
                <span>Project</span>
                <select value={newResearchSpaceProjectId} onChange={(event) => setNewResearchSpaceProjectId(event.target.value)}>
                  <option value="">None</option>
                  {visibleResearchProjects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.code} · {project.title}
                    </option>
                  ))}
                </select>
              </label>
              {newResearchSpaceError ? <p className="error">{newResearchSpaceError}</p> : null}
              <div className="research-space-form-actions">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    setNewResearchSpaceOpen(false);
                    setEditingResearchSpaceId(null);
                  }}
                  disabled={savingResearchSpace}
                >
                  Cancel
                </button>
                <button type="button" onClick={() => void handleSaveResearchSpace()} disabled={savingResearchSpace}>
                  {savingResearchSpace ? "Saving..." : editingResearchSpaceId ? "Save" : "Create"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      {profileOpen && currentUser ? (
        <UserProfileModal
          currentUser={currentUser}
          onClose={() => setProfileOpen(false)}
          onUpdated={(updatedUser) => {
            setMe((prev) => prev ? { ...prev, user: updatedUser } : prev);
          }}
        />
      ) : null}
      {cmdPaletteOpen ? (
        <CommandPalette
          items={cmdPaletteItems}
          onSelect={(id) => {
            setCmdPaletteOpen(false);
            handleNavigate(id as View);
          }}
          onClose={() => setCmdPaletteOpen(false)}
        />
      ) : null}
      {workspaceSwitcherOpen ? (
        <CommandPalette
          items={workspaceSwitcherItems}
          onSelect={(id) => {
            setWorkspaceSwitcherOpen(false);
            switchWorkspaceFamily(id as WorkspaceFamily);
          }}
          onClose={() => setWorkspaceSwitcherOpen(false)}
        />
      ) : null}
      {shortcutHudVisible ? (
        <div className="shortcut-hud" aria-hidden="true">
          <div className="shortcut-hud-list">
            {shortcutHints.map((item: { key: string; label: string }) => (
              <div key={`${item.key}-${item.label}`} className="shortcut-hud-row">
                <span className="shortcut-hud-key">{item.key}</span>
                <span className="shortcut-hud-label">{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <GuidedTour
        open={researchTourOpen}
        steps={researchTourSteps}
        stepIndex={researchTourStepIndex}
        onBack={() => setResearchTourStepIndex((current) => Math.max(0, current - 1))}
        onNext={() => setResearchTourStepIndex((current) => Math.min(researchTourSteps.length - 1, current + 1))}
        onSkip={completeResearchTour}
        onFinish={completeResearchTour}
      />
      {suggestionPanelOpen ? (
        <div className="modal-overlay" onClick={() => !savingSuggestion && setSuggestionPanelOpen(false)}>
          <div className="modal-card suggestion-panel" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              {suggestionPanelView === "create" ? (
                <button type="button" className="ghost icon-only" onClick={() => setSuggestionPanelView("list")}>
                  <FontAwesomeIcon icon={faArrowLeft} />
                </button>
              ) : null}
              <h3>{suggestionPanelView === "create" ? "New Suggestion" : "Suggestions"}</h3>
              <div className="modal-head-actions">
                {suggestionPanelView === "list" ? (
                  <button type="button" className="meetings-new-btn" onClick={() => setSuggestionPanelView("create")}>
                    <FontAwesomeIcon icon={faPlus} /> New
                  </button>
                ) : (
                  <button type="button" className="meetings-new-btn" disabled={!suggestionContent.trim() || savingSuggestion} onClick={() => void handleCreateSuggestion()}>
                    {savingSuggestion ? "Sending..." : "Submit"}
                  </button>
                )}
                <button type="button" className="ghost docs-action-btn" title="Close" onClick={() => setSuggestionPanelOpen(false)}>
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
            </div>

            {suggestionPanelView === "list" ? (
              <div className="suggestion-list-wrap">
                <div className="suggestion-filters">
                  {["", "new", "doing", "done", "rejected"].map((s) => (
                    <button
                      key={s}
                      type="button"
                      className={`suggestion-filter-btn ${suggestionStatusFilter === s ? "active" : ""}`}
                      onClick={() => { setSuggestionStatusFilter(s); void loadMySuggestions(s); }}
                    >
                      {s || "All"}
                    </button>
                  ))}
                </div>
                {mySuggestionsLoading ? (
                  <div className="suggestion-empty">Loading...</div>
                ) : mySuggestions.length === 0 ? (
                  <div className="suggestion-empty">No suggestions yet. Click "New" to create one.</div>
                ) : (
                  <div className="suggestion-items">
                    {mySuggestions.map((s) => (
                      <div key={s.id} className="suggestion-item">
                        <div className="suggestion-item-header">
                          <span className={`suggestion-category-badge ${s.category}`}>
                            {s.category === "bug" ? <FontAwesomeIcon icon={faBug} /> : null}
                            {s.category}
                          </span>
                          <span className={`suggestion-status-badge ${s.status}`}>{s.status}</span>
                        </div>
                        <p className="suggestion-item-content">{s.content}</p>
                        <span className="suggestion-item-date">{new Date(s.created_at).toLocaleDateString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="form-grid">
                <label className="full-span">
                  Type
                  <div className="suggestion-category-select">
                    {(["bug", "feature", "enhancement"] as UserSuggestionCategory[]).map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        className={`suggestion-category-option ${suggestionCategory === cat ? "active" : ""}`}
                        onClick={() => setSuggestionCategory(cat)}
                      >
                        {cat === "bug" ? <FontAwesomeIcon icon={faBug} /> : null}
                        {cat === "feature" ? <FontAwesomeIcon icon={faLightbulb} /> : null}
                        {cat === "enhancement" ? <FontAwesomeIcon icon={faWrench} /> : null}
                        {cat}
                      </button>
                    ))}
                  </div>
                </label>
                <label className="full-span">
                  Description
                  <textarea rows={6} value={suggestionContent} onChange={(event) => setSuggestionContent(event.target.value)} placeholder="Describe your suggestion..." />
                </label>
              </div>
            )}
          </div>
        </div>
      ) : null}
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "var(--bg-elevated)",
            border: "1px solid var(--line-strong)",
            color: "var(--text)",
            fontFamily: "var(--font)",
            fontSize: "12px",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-md)",
          },
        }}
        theme="dark"
      />
    </div>
  );
}
