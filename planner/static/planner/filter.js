// Live-filter any list: an <input data-filter="listId"> hides rows in #listId
// (elements carrying a data-name) that don't contain the typed text.
document.querySelectorAll("[data-filter]").forEach((input) => {
  const list = document.getElementById(input.dataset.filter);
  input.addEventListener("input", () => {
    const query = input.value.toLowerCase();
    list.querySelectorAll("[data-name]").forEach((row) => {
      row.hidden = !row.dataset.name.toLowerCase().includes(query);
    });
  });
});
