// Manage dropdowns showing available camera groups

/**
 * Populate group selectors with options from the server.
 * @returns {Promise<void>} Resolved when options are loaded.
 */
export async function loadGroups() {
  const groupDropdown =
    document.getElementById("group-dropdown") ||
    document.getElementById("cost-group");
  const groupsSelect = document.getElementById("groups");
  const groupDatalist = document.getElementById("group-options");
  if (!groupDropdown && !groupsSelect) return;
  if (groupDropdown) {
    groupDropdown.innerHTML = '<option value="all">Loading groups...</option>';
    groupDropdown.disabled = true;
  }
  if (groupsSelect) {
    groupsSelect.disabled = true;
    if (groupDatalist) groupDatalist.innerHTML = "";
  }

  try {
    const response = await fetch("/groups");
    const groups = await response.json();
    if (groupDropdown) {
      groupDropdown.innerHTML = '<option value="all">All Groups</option>';
    }
    if (groupsSelect && groupDatalist) {
      groupDatalist.innerHTML = "";
    }
    groups.forEach((group) => {
      if (groupDropdown) {
        const option = document.createElement("option");
        option.value = group;
        option.textContent = group;
        groupDropdown.appendChild(option);
      }
      if (groupsSelect && groupDatalist) {
        const option = document.createElement("option");
        option.value = group;
        groupDatalist.appendChild(option);
      }
    });
  } catch (error) {
    console.error("Error loading groups:", error);
    if (groupDropdown) {
      groupDropdown.innerHTML = '<option value="all">All Groups</option>';
    }
    if (groupsSelect && groupDatalist) {
      groupDatalist.innerHTML = "";
    }
  } finally {
    if (groupDropdown) groupDropdown.disabled = false;
    if (groupsSelect) groupsSelect.disabled = false;
  }
}

/**
 * Determine the group currently selected by the user.
 * @returns {string} Selected group name or 'all' when none.
 */
export function getSelectedGroup() {
  const dropdown = document.getElementById("group-dropdown");
  if (dropdown && dropdown.value) return dropdown.value;
  const navDropdown = document.getElementById("nav-group-dropdown");
  if (navDropdown && navDropdown.value) return navDropdown.value;
  if (window.currentGroup) return window.currentGroup;
  return "all";
}
