document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('log-filter-form');
    const table = document.getElementById('log-table');

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(form);
        const searchParams = new URLSearchParams(formData);

        fetch(`/logs?${searchParams.toString()}`)
            .then(response => response.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newTable = doc.getElementById('log-table');
                const newPagination = doc.querySelector('.pagination');

                table.innerHTML = newTable.innerHTML;
                document.querySelector('.pagination').innerHTML = newPagination.innerHTML;
            })
            .catch(error => console.error('Error:', error));
    });
});