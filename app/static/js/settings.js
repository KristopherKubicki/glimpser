// app/static/js/settings.js

document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('settingsSearch');
    const settingsTableBody = document.getElementById('settingsTableBody');
    const settingsRows = Array.from(settingsTableBody.getElementsByTagName('tr'));

    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();

        settingsRows.forEach(row => {
            const settingName = row.cells[0].textContent.toLowerCase();
            const settingValue = row.cells[1].querySelector('input').value.toLowerCase();

            if (settingName.includes(searchTerm) || settingValue.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    });
});