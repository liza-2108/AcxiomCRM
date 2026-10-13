function confirmDelete() {
    return window.confirm("Are you sure you want to delete this record?");
}
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(function (form) {
        form.addEventListener("submit", function () {
            const submit = form.querySelector('button[type="submit"], button:not([type])');
            if (submit && !submit.dataset.noLoading) {
                submit.disabled = true;
                submit.dataset.originalText = submit.innerText;
                submit.innerText = "Please wait...";
                setTimeout(() => { submit.disabled = false; submit.innerText = submit.dataset.originalText; }, 4000);
            }
        });
    });
});
