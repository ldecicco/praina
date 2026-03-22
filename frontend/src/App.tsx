import { useCallback, useEffect, useRef, useState } from "react";
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
  faClipboardCheck,
  faComments,
  faGear,
  faLayerGroup,
  faPen,
  faRightFromBracket,
  faSearch,
  faSitemap,
  faSquareCheck,
  faUserShield,
  faFileLines,
  faFlask,
  faGraduationCap,
  faUsers,
  faWrench,
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
import { TeachingCoursesWorkspace } from "./components/TeachingCoursesWorkspace";
import { TeachingWorkspace } from "./components/TeachingWorkspace";
import { NewProjectModal } from "./components/NewProjectModal";
import { ProjectSettingsModal } from "./components/ProjectSettingsModal";
import { UserProfileModal } from "./components/UserProfileModal";
import { api, PROJECT_DATA_CHANGED_EVENT } from "./lib/api";
import { currentProjectMonth } from "./lib/utils";
import prainaLogoWhite from "./assets/praina-logo-white.svg";
import { useAutoRefresh } from "./lib/useAutoRefresh";
import type { AppNotification, AuthTokens, MeResponse, Project, ProposalCallBrief } from "./types";

type View = "my-work" | "dashboard" | "call" | "proposal" | "submission" | "delivery" | "workbench" | "meetings" | "project-chat" | "assistant" | "wizard" | "matrix" | "documents" | "planning" | "admin" | "todos" | "search" | "research" | "teaching" | "courses";
const ASSISTANT_PENDING_PROMPT_KEY = "assistant_pending_prompt";
const ACTIVE_PROJECT_KEY = "active_project_id";
const SIDEBAR_COLLAPSED_KEY = "sidebar_collapsed";
const ACCESS_TOKEN_KEY = "auth_access_token";
const REFRESH_TOKEN_KEY = "auth_refresh_token";

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
};

export default function App() {
  const [platformSection, setPlatformSection] = useState<"research" | "teaching">("research");
  const [view, setView] = useState<View>("dashboard");
  const [projects, setProjects] = useState<Project[]>([]);
  const [authTokens, setAuthTokens] = useState<AuthTokens | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    () => (typeof window !== "undefined" ? window.sessionStorage.getItem(ACTIVE_PROJECT_KEY) || "" : "")
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(
    () => typeof window !== "undefined" && window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1"
  );
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [projectSettingsOpen, setProjectSettingsOpen] = useState(false);
  const [error, setError] = useState("");
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifDropdownOpen, setNotifDropdownOpen] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const notifDropdownRef = useRef<HTMLDivElement>(null);
  const [pendingDocumentKey, setPendingDocumentKey] = useState<string | null>(null);
  const [pendingMeetingId, setPendingMeetingId] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [proposalCallBrief, setProposalCallBrief] = useState<ProposalCallBrief | null>(null);

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
      setSelectedProjectId("");
      return;
    }
    void loadProjects();
  }, [me?.user.id]);

  function handleAuthenticated(tokens: AuthTokens, meResponse: MeResponse) {
    api.setAuthToken(tokens.access_token);
    setAuthTokens(tokens);
    setMe(meResponse);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
      window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    }
    void loadProjects();
  }

  function handleLogout() {
    api.setAuthToken(null);
    setAuthTokens(null);
    setMe(null);
    setProjects([]);
    setSelectedProjectId("");
    setError("");
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(ACCESS_TOKEN_KEY);
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
      window.sessionStorage.removeItem(ACTIVE_PROJECT_KEY);
    }
  }

  function handleProjectCreated(project: Project) {
    setSelectedProjectId(project.id);
    if (project.project_kind === "teaching") {
      setPlatformSection("teaching");
      setView("teaching");
    } else if (project.project_mode === "proposal") {
      setPlatformSection("research");
      setView("call");
    }
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, project.id);
    }
    void loadProjects();
  }

  function handleProjectUpdated(project: Project) {
    setSelectedProjectId(project.id);
    setPlatformSection(project.project_kind === "teaching" ? "teaching" : "research");
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

  function handleSelectProject(projectId: string) {
    setSelectedProjectId(projectId);
    const selected = projects.find((project) => project.id === projectId);
    if (selected) {
      setPlatformSection(selected.project_kind === "teaching" ? "teaching" : "research");
    }
    if (typeof window !== "undefined") {
      if (projectId) window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, projectId);
      else window.sessionStorage.removeItem(ACTIVE_PROJECT_KEY);
    }
  }

  const stableLoadProjects = useCallback(() => { void loadProjects(); }, [me?.user.id]);
  useAutoRefresh(stableLoadProjects);

  function handleNavigate(targetView: View, entityId?: string) {
    if (targetView === "documents" && entityId) {
      setPendingDocumentKey(entityId);
    } else if (targetView === "meetings" && entityId) {
      setPendingMeetingId(entityId);
    }
    setView(targetView);
  }

  function openAssistantWithPrompt(prompt: string) {
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(ASSISTANT_PENDING_PROMPT_KEY, prompt);
    }
    setView("assistant");
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

  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false);
  const projectDropdownRef = useRef<HTMLDivElement>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(event.target as Node)) {
        setProjectDropdownOpen(false);
      }
      if (notifDropdownRef.current && !notifDropdownRef.current.contains(event.target as Node)) {
        setNotifDropdownOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (projectDropdownOpen || notifDropdownOpen || userMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [projectDropdownOpen, notifDropdownOpen, userMenuOpen]);

  const activeProject = projects.find((project) => project.id === selectedProjectId) ?? null;

  useEffect(() => {
    if (view === "courses" || view === "teaching") {
      setPlatformSection("teaching");
      return;
    }
    if (view === "research" || view === "call" || view === "proposal" || view === "submission") {
      setPlatformSection("research");
      return;
    }
    if (activeProject) {
      setPlatformSection(activeProject.project_kind === "teaching" ? "teaching" : "research");
    }
  }, [activeProject?.id, activeProject?.project_kind, view]);

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
    if (!selectedProjectId || activeProject?.project_mode !== "proposal") {
      setProposalCallBrief(null);
      return;
    }
    api.getProposalCallBrief(selectedProjectId)
      .then((res) => setProposalCallBrief(res))
      .catch(() => setProposalCallBrief(null));
  }, [selectedProjectId, activeProject?.project_mode]);

  // Redirect to dashboard if on an execution-only view while in proposal mode
  useEffect(() => {
    if (activeProject?.project_mode === "proposal") {
      const proposalViews = new Set<View>(["my-work", "courses", "dashboard", "call", "proposal", "submission", "project-chat", "assistant", "wizard", "admin"]);
      if (!proposalViews.has(view)) {
        setView("dashboard");
      }
    }
  }, [activeProject?.project_mode, view]);

  useEffect(() => {
    if (activeProject?.project_kind === "teaching") {
      const teachingViews = new Set<View>(["my-work", "courses", "dashboard", "teaching", "project-chat", "assistant", "todos", "search", "admin"]);
      if (!teachingViews.has(view)) {
        setView("teaching");
      }
    }
  }, [activeProject?.project_kind, view]);

  const viewTitle: Record<View, string> = {
    "my-work": "My Work",
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
    research: "Research",
    teaching: "Teaching",
    courses: "Courses",
    admin: "Admin",
  };

  const ALWAYS_VISIBLE_VIEWS = new Set<View>(["my-work"]);
  const PROPOSAL_MODE_VIEWS = new Set<View>(["dashboard", "call", "proposal", "submission", "project-chat", "assistant", "wizard", "search", "admin"]);
  const TEACHING_MODE_VIEWS = new Set<View>(["courses", "teaching", "project-chat", "assistant", "todos", "search", "admin"]);
  const EXECUTION_MODE_HIDDEN = new Set<View>(["proposal"]);
  const researchNavItems: Array<{ id: View; label: string; icon: typeof faSitemap }> = [
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
  const teachingNavItems: Array<{ id: View; label: string; icon: typeof faSitemap }> = [
    { id: "courses", label: "Courses", icon: faBook },
    { id: "teaching", label: "Projects", icon: faGraduationCap },
    { id: "project-chat", label: "Chat", icon: faUsers },
    { id: "assistant", label: "Assistant", icon: faComments },
    { id: "todos", label: "Todos", icon: faSquareCheck },
    { id: "search", label: "Search", icon: faSearch },
  ];

  const isProposalMode = activeProject?.project_mode === "proposal";
  const isTeachingProject = activeProject?.project_kind === "teaching";
  const visibleProjects = projects.filter((project) =>
    platformSection === "teaching" ? project.project_kind === "teaching" : project.project_kind !== "teaching"
  );
  const currentUser = me?.user ?? null;
  const canAccessResearch = currentUser?.can_access_research ?? false;
  const canAccessTeaching = currentUser?.can_access_teaching ?? false;
  const availableSections = [
    ...(canAccessResearch ? (["research"] as const) : []),
    ...(canAccessTeaching ? (["teaching"] as const) : []),
  ];
  const isSuperAdmin = currentUser?.platform_role === "super_admin";
  const proposalCallReady = Boolean(proposalCallBrief?.source_call_id || proposalCallBrief?.call_title?.trim());
  const navSections =
    platformSection === "teaching"
      ? canAccessTeaching
        ? [
            {
              label: "Teaching",
              items: teachingNavItems.filter((item) => ALWAYS_VISIBLE_VIEWS.has(item.id) || TEACHING_MODE_VIEWS.has(item.id)),
            },
          ]
        : []
      : canAccessResearch
        ? [
            {
              label: "Research",
              items: researchNavItems.filter((item) => ALWAYS_VISIBLE_VIEWS.has(item.id) || (isProposalMode ? PROPOSAL_MODE_VIEWS.has(item.id) : !EXECUTION_MODE_HIDDEN.has(item.id))),
            },
          ]
        : [];

  function switchPlatformSection(nextSection: "research" | "teaching") {
    if ((nextSection === "research" && !canAccessResearch) || (nextSection === "teaching" && !canAccessTeaching)) {
      return;
    }
    setPlatformSection(nextSection);
    if (nextSection === "teaching") {
      setView("courses");
      return;
    }
    const researchProject = projects.find((project) => project.project_kind !== "teaching");
    if (activeProject?.project_kind === "teaching" && researchProject) {
      setSelectedProjectId(researchProject.id);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(ACTIVE_PROJECT_KEY, researchProject.id);
      }
    }
    setView("research");
  }
  function isNavItemDisabled(itemId: View): boolean {
    if (!isProposalMode) return false;
    if (!proposalCallReady) return itemId !== "call";
    return false;
  }

  const canCreateProjects = currentUser
    ? (currentUser.platform_role === "super_admin" || currentUser.platform_role === "project_creator") &&
      (platformSection === "teaching" ? canAccessTeaching : canAccessResearch)
    : false;
  const userInitials =
    currentUser?.display_name
      .split(" ")
      .map((part) => part[0]?.toUpperCase() || "")
      .slice(0, 2)
      .join("") || "U";
  const activeProjectMonth = currentProjectMonth(activeProject?.start_date);

  useEffect(() => {
    if (!currentUser) return;
    if (platformSection === "research" && !canAccessResearch && canAccessTeaching) {
      setPlatformSection("teaching");
      setView("courses");
      return;
    }
    if (platformSection === "teaching" && !canAccessTeaching && canAccessResearch) {
      setPlatformSection("research");
      setView("research");
    }
  }, [currentUser?.id, platformSection, canAccessResearch, canAccessTeaching]);

  if (!currentUser || !authTokens) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className={`app-frame ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="app-sidebar">
        <div className="sidebar-header">
          <button type="button" className="icon-button" onClick={toggleSidebar} aria-label="Toggle sidebar">
            {sidebarCollapsed ? (
              <img src={prainaLogoWhite} alt="Praina" style={{ height: 18, width: 'auto' }} />
            ) : (
              <FontAwesomeIcon icon={faChevronLeft} />
            )}
          </button>
          {!sidebarCollapsed ? (
            <div className="brand-block">
              <img src={prainaLogoWhite} alt="Praina" className="brand-logo" />
              <span className="brand-wordmark">Praina</span>
            </div>
          ) : null}
        </div>

        <nav className="app-nav">
          {navSections.map((section) => (
            <div key={section.label} className="app-nav-section">
              {!sidebarCollapsed ? <div className="app-nav-section-label">{section.label}</div> : null}
              {section.items.map((item) => {
                const active = view === item.id;
                const disabled = isNavItemDisabled(item.id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`app-nav-item ${active ? "active" : ""} ${disabled ? "disabled" : ""}`}
                    onClick={() => !disabled && setView(item.id)}
                    title={sidebarCollapsed ? item.label : undefined}
                    disabled={disabled}
                  >
                    <span className="app-nav-icon">
                      <FontAwesomeIcon icon={item.icon} />
                    </span>
                    {!sidebarCollapsed ? <span className="app-nav-label">{item.label}</span> : null}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer" />
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <h2>{viewTitle[view]}</h2>
            {availableSections.length > 1 ? (
              <div className="topbar-section-toggle" role="tablist" aria-label="Platform section">
                {canAccessResearch ? (
                  <button
                    type="button"
                    className={`topbar-section-btn ${platformSection === "research" ? "active" : ""}`}
                    onClick={() => switchPlatformSection("research")}
                    aria-pressed={platformSection === "research"}
                  >
                    <FontAwesomeIcon icon={faFlask} />
                    <span>Research</span>
                  </button>
                ) : null}
                {canAccessTeaching ? (
                  <button
                    type="button"
                    className={`topbar-section-btn ${platformSection === "teaching" ? "active" : ""}`}
                    onClick={() => switchPlatformSection("teaching")}
                    aria-pressed={platformSection === "teaching"}
                  >
                    <FontAwesomeIcon icon={faGraduationCap} />
                    <span>Teaching</span>
                  </button>
                ) : null}
              </div>
            ) : null}
            {view !== "courses" ? (
            <div className="topbar-project-dropdown" ref={projectDropdownRef}>
              <button
                type="button"
                className="topbar-project-trigger"
                onClick={() => setProjectDropdownOpen((prev) => !prev)}
              >
                {activeProject ? (
                  <>
                    <strong>{activeProject.code}</strong>
                    <span>{activeProject.title}</span>
                    <span className="topbar-project-status">{isProposalMode ? "Proposal" : isTeachingProject ? "Teaching" : activeProjectMonth ? `M${activeProjectMonth}` : "-"}</span>
                  </>
                ) : (
                  <span className="topbar-project-placeholder">Select project</span>
                )}
                <FontAwesomeIcon icon={faChevronDown} className={`topbar-chevron ${projectDropdownOpen ? "open" : ""}`} />
              </button>
              {projectDropdownOpen ? (
                <div className="topbar-project-menu">
                  {visibleProjects.map((project) => (
                    <button
                      key={project.id}
                      type="button"
                      className={`topbar-project-option ${project.id === selectedProjectId ? "active" : ""}`}
                      onClick={() => {
                        handleSelectProject(project.id);
                        setProjectDropdownOpen(false);
                      }}
                    >
                      <strong>{project.code}</strong>
                      <span>{project.title}</span>
                      <span className="topbar-option-status">{project.status}</span>
                    </button>
                  ))}
                  {visibleProjects.length === 0 ? (
                    <div className="topbar-project-empty">No projects</div>
                  ) : null}
                </div>
              ) : null}
            </div>
            ) : null}
            <button
              type="button"
              className="ghost icon-only"
              title="Project settings"
              onClick={() => setProjectSettingsOpen(true)}
              disabled={!activeProject || view === "courses"}
            >
              <FontAwesomeIcon icon={faGear} />
            </button>
            {canCreateProjects ? (
              <button type="button" className="ghost icon-text-button" onClick={() => setNewProjectOpen(true)}>
                + New Project
              </button>
            ) : null}
          </div>

          <div className="topbar-right">
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
            <button
              type="button"
              className="ghost icon-only"
              title="Admin Tools"
              onClick={() => setView("admin")}
              disabled={!isSuperAdmin}
            >
              <FontAwesomeIcon icon={faUserShield} />
            </button>
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
          {view === "my-work" ? <MyWork /> : null}
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
              selectedProjectId={selectedProjectId}
              currentUser={currentUser}
              accessToken={authTokens.access_token}
            />
          ) : null}
          {view === "assistant" ? <ChatWorkspace selectedProjectId={selectedProjectId} project={activeProject} onNavigate={(v, id) => handleNavigate(v as View, id)} /> : null}
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
          {view === "research" ? <ResearchWorkspace selectedProjectId={selectedProjectId} /> : null}
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
        platformSection={platformSection}
        onClose={() => setNewProjectOpen(false)}
        onProjectCreated={handleProjectCreated}
      />
      {profileOpen && currentUser ? (
        <UserProfileModal
          currentUser={currentUser}
          onClose={() => setProfileOpen(false)}
          onUpdated={(updatedUser) => {
            setMe((prev) => prev ? { ...prev, user: updatedUser } : prev);
          }}
        />
      ) : null}
    </div>
  );
}
