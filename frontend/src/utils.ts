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
