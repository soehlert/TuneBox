export const getLocalUsername = (): string | null => {
  const adminName = localStorage.getItem("tunebox_admin_name");
  if (adminName) return adminName;
  
  const guestStr = localStorage.getItem("tunebox_guest");
  if (guestStr) {
    try {
      const guest = JSON.parse(guestStr);
      return guest.name;
    } catch {
      return null;
    }
  }
  
  const adminToken = localStorage.getItem("tunebox_admin_token");
  if (adminToken) {
    return localStorage.getItem("tunebox_instance_name") || "Admin";
  }
  
  return null;
};
