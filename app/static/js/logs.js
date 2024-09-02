document.addEventListener('DOMContentLoaded', function() {
    console.log('Logs page loaded');
    const form = document.getElementById('log-filter-form');
    const table = document.getElementById('log-table');

    if (!form) {
        console.error('Log filter form not found');
        return;
    }

    if (!table) {
        console.error('Log table not found');
        return;
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        console.log('Form submitted');
        const formData = new FormData(form);
        const searchParams = new URLSearchParams(formData);

        fetch(`/logs?${searchParams.toString()}`)
            .then(response => {
                console.log('Response status:', response.status);
                return response.text();
            })
            .then(html => {
                console.log('Response received');
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newTable = doc.getElementById('log-table');
                const newPagination = doc.querySelector('.pagination');

                if (newTable) {
                    table.innerHTML = newTable.innerHTML;
                } else {
                    console.error('New log table not found in response');
                }

                const paginationElement = document.querySelector('.pagination');
                if (newPagination && paginationElement) {
                    paginationElement.innerHTML = newPagination.innerHTML;
                } else {
                    console.error('Pagination element not found');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred while fetching logs. Please try again.');
            });
    });
});