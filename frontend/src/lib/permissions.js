export function canManageOperations(user) {
  return user?.role === "admin" || user?.role === "manager";
}
