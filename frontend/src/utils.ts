export const getClientId = (): string => {
  let cid = localStorage.getItem("tunebox_client_id");
  if (!cid) {
    cid = typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Math.random().toString(36).substring(2) + Date.now().toString(36);
    localStorage.setItem("tunebox_client_id", cid);
  }
  return cid;
};

export const getLocalUsername = (): string => {
  const adminToken = localStorage.getItem("tunebox_admin_token");
  if (adminToken) {
    const adminName = localStorage.getItem("tunebox_admin_name");
    return adminName || "Admin";
  }
  
  const guestStr = localStorage.getItem("tunebox_guest");
  if (guestStr) {
    try {
      const guest = JSON.parse(guestStr);
      if (guest.name) return guest.name;
    } catch {
      // ignore JSON parse error
    }
  }
  
  return `Guest-${getClientId().substring(0, 6)}`;
};

export const getApiUrl = (path: string) => {
  return `${window.location.origin}${path}`;
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
