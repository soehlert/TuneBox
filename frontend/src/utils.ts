export const getLocalUsername = (): string | null => {
  const adminName = localStorage.getItem("tunebox_admin_name");
  if (adminName) return adminName;
  
  const guestStr = localStorage.getItem("tunebox_guest");
  if (guestStr) {
    try {
      const guest = JSON.parse(guestStr);
      if (guest.name) return guest.name;
    } catch {
      // ignore JSON parse error
    }
  }
  
  const adminToken = localStorage.getItem("tunebox_admin_token");
  if (adminToken) {
    return "Admin";
  }
  
  return null;
};

export const getApiUrl = (path: string) => {
  const isDev = window.location.port === "5173";
  const base = isDev ? `http://${window.location.hostname}:8000` : window.location.origin;
  return `${base}${path}`;
};

export const getSortKey = (name: string): string => {
  if (!name) return "";
  const trimmed = name.trim();
  if (/^the\s+/i.test(trimmed)) {
    return trimmed.replace(/^the\s+/i, "").trim();
  }
  return trimmed;
};

export const triggerQueueToast = (message: string, severity: "success" | "warning" | "error" = "success") => {
  window.dispatchEvent(new CustomEvent("tunebox_queue_toast", { detail: { message, severity } }));
};
