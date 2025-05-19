function updateCartCount() {
    const cart = JSON.parse(localStorage.getItem('cart')) || [];
    const cartCount = cart.length;
    const cartCountElement = document.getElementById('cart-count');
    if (cartCountElement) {
        cartCountElement.textContent = cartCount;
    }
}

async function checkSeatAvailability(matchId, sectorName, row, seat) {
    try {
        const response = await fetch(`/check_seat/${matchId}/${sectorName}/${row}/${seat}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        if (response.ok) {
            const data = await response.json();
            return data.available;
        }
        return false;
    } catch (error) {
        console.error('Error checking seat availability:', error);
        return false;
    }
}

function updateCart(cart) {
    localStorage.setItem('cart', JSON.stringify(cart));
    updateCartCount();
}


// Код из admin_login
var gk_isXlsx = false;
var gk_xlsxFileLookup = {};
var gk_fileData = {};
function filledCell(cell) {
  return cell !== '' && cell != null;
}
function loadFileData(filename) {
  if (gk_isXlsx && gk_xlsxFileLookup[filename]) {
    try {
      var workbook = XLSX.read(gk_fileData[filename], { type: 'base64' });
      var firstSheetName = workbook.SheetNames[0];
      var worksheet = workbook.Sheets[firstSheetName];
      // Convert sheet to JSON to filter blank rows
      var jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1, blankrows: false, defval: '' });
      // Filter out blank rows (rows where all cells are empty, null, or undefined)
      var filteredData = jsonData.filter(row => row.some(filledCell));
      // Heuristic to find the header row by ignoring rows with fewer filled cells than the next row
      var headerRowIndex = filteredData.findIndex((row, index) =>
        row.filter(filledCell).length >= filteredData[index + 1]?.filter(filledCell).length
      );
      // Fallback
      if (headerRowIndex === -1 || headerRowIndex > 25) {
        headerRowIndex = 0;
      }
      // Convert filtered JSON back to CSV
      var csv = XLSX.utils.aoa_to_sheet(filteredData.slice(headerRowIndex)); // Create a new sheet from filtered array of arrays
      csv = XLSX.utils.sheet_to_csv(csv, { header: 1 });
      return csv;
    } catch (e) {
      console.error(e);
      return "";
    }
  }
  return gk_fileData[filename] || "";
}


// admin_panel
function filterMatches() {
    const dateFrom = document.getElementById('date-from').value;
    const dateTo = document.getElementById('date-to').value;
    const tournamentFilter = document.getElementById('tournament-filter').value;
    const searchQuery = document.getElementById('search-query').value.toLowerCase();
    const matchCards = document.querySelectorAll('.match-card');
    matchCards.forEach(card => {
        const matchDate = card.dataset.date;
        const matchTournament = card.dataset.tournament;
        const matchTeams = card.querySelector('.match-teams').textContent.toLowerCase();
        let dateMatch = true;
        if (dateFrom && matchDate < dateFrom) {
            dateMatch = false;
        }
        if (dateTo && matchDate > dateTo) {
            dateMatch = false;
        }
        const tournamentMatch = tournamentFilter === 'all' || matchTournament === tournamentFilter;
        const searchMatch = searchQuery === '' || matchTeams.includes(searchQuery);
        if (dateMatch && tournamentMatch && searchMatch) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

function deleteMatch(matchId) {
    if (!confirm("Вы уверены, что хотите удалить этот матч?")) {
        return;
    }

    fetch(`/admin-panel/delete_match/${matchId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Ошибка удаления');
        }
        return response;
    })
    .then(() => {
        window.location.href = "/admin-panel";
    })
    .catch(error => {
        console.error("Ошибка:", error);
        alert("Не удалось удалить матч");
    });
}

function toggleShowInactive() {
    const showInactive = document.getElementById('show-inactive').checked;
    const url = new URL(window.location.href);
    if (showInactive) {
        url.searchParams.set('show_inactive', '1');
    } else {
        url.searchParams.delete('show_inactive');
    }
    window.location.href = url.toString();
}

function adminPanelOnLoad() {
    filterMatches();
}



// bulk_add_sectors.html
function addRow() {
    const tbody = document.getElementById('sector-rows');
    const firstRow = tbody.querySelector('tr');
    const newRow = firstRow.cloneNode(true);
    newRow.querySelectorAll('input').forEach(input => input.value = '');
    tbody.appendChild(newRow);
}

function removeRow(btn) {
    const tbody = document.getElementById('sector-rows');
    if (tbody.rows.length > 1) {
        btn.closest('tr').remove();
    }
}




// cart.html
let cart = JSON.parse(localStorage.getItem('cart')) || [];
const RESERVATION_DURATION = 15 * 60 * 1000;

async function validateCart(matches) {
    const invalidSeats = [];
    for (let i = cart.length - 1; i >= 0; i--) {
        const item = cart[i];
        const now = Date.now();
        if (now - item.reservationTime > RESERVATION_DURATION) {
            invalidSeats.push(i);
            continue;
        }
        const isAvailable = await checkSeatAvailability(item.match_id, item.sector_name, item.row, item.seat);
        if (!isAvailable) {
            invalidSeats.push(i);
        }
    }
    invalidSeats.forEach(index => cart.splice(index, 1));
    updateCart(cart);
    renderCart(matches);
}

function removeFromCart(index, matches) {
    cart.splice(index, 1);
    updateCart(cart);
    renderCart(matches);
}

function clearCart(matches) {
    cart = [];
    updateCart(cart);
    renderCart(matches);
}

function renderCart(matches) {
    const cartContainer = document.getElementById('cart-items');
    const totalPriceElement = document.getElementById('total-price');
    cartContainer.innerHTML = '';

    if (cart.length === 0) {
        cartContainer.innerHTML = '<p class="text-gray-500">Корзина пуста.</p>';
        totalPriceElement.textContent = '0 ₽';
        return;
    }

    let totalPrice = 0;
    cart.forEach((item, index) => {
        const remainingTime = Math.max(0, Math.floor((RESERVATION_DURATION - (Date.now() - item.reservationTime)) / 1000));
        const minutes = Math.floor(remainingTime / 60);
        const seconds = remainingTime % 60;
        const timeLeft = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;

        // Находим матч по slug
        const match = matches.find(m => m.slug === item.match_id);
        let matchInfo = '';
        if (match) {
            matchInfo = `<p class="font-semibold">Матч: <a href="/tickets/${match.slug}" class="text-blue-500 hover:underline">${match.teams}</a></p>`;
        } else {
            matchInfo = `<p class="font-semibold">Матч: <span class="text-red-500">Не найден</span></p>`;
        }

        const cartItem = document.createElement('div');
        cartItem.className = 'cart-item';
        cartItem.innerHTML = `
            <div class="flex justify-between items-center">
                <div>
                    ${matchInfo}
                    <p>Сектор: ${item.sector_name}</p>
                    <p>Ряд: ${item.row}, Место: ${item.seat}</p>
                    <p>Цена: ${item.price} ₽</p>
                    <p>Осталось времени: <span id="time-${index}">${timeLeft}</span></p>
                </div>
                <button class="remove-button" onclick="removeFromCart(${index}, window.cartMatches)">Удалить</button>
            </div>
        `;
        cartContainer.appendChild(cartItem);
        totalPrice += item.price;
    });

    totalPriceElement.textContent = `${totalPrice} ₽`;
}

function showNotification(message) {
    let notif = document.createElement('div');
    notif.textContent = message;
    notif.style.position = 'fixed';
    notif.style.top = '30px';
    notif.style.left = '50%';
    notif.style.transform = 'translateX(-50%)';
    notif.style.background = '#34C759';
    notif.style.color = '#fff';
    notif.style.padding = '12px 24px';
    notif.style.borderRadius = '8px';
    notif.style.fontWeight = 'bold';
    notif.style.zIndex = 9999;
    document.body.appendChild(notif);
    setTimeout(function() { notif.remove(); }, 1200);
}

async function submitCheckout(matches) {
    const form = document.getElementById('checkout-form');
    const fullName = form.querySelector('#full_name').value;
    const email = form.querySelector('#email').value;
    const phone = form.querySelector('#phone').value;

    if (!fullName || !email || !phone) {
        alert('Пожалуйста, заполните все обязательные поля.');
        return;
    }

    const selectedSeats = JSON.stringify(cart);
    const formData = new FormData();
    formData.append('full_name', fullName);
    formData.append('email', email);
    formData.append('phone', phone);
    formData.append('selected_seats', selectedSeats);

    try {
        const response = await fetch('/checkout', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            cart = [];
            updateCart(cart);
            showNotification('Заказ успешно оформлен!');
            window.location.href = '/cart?success=true';
        } else {
            const errorText = await response.text();
            showNotification(`Ошибка при оформлении заказа: ${errorText}`);
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showNotification('Произошла ошибка при оформлении заказа.');
    }
}

function cartOnLoad(matches) {
    window.cartMatches = matches;
    validateCart(matches);
    setInterval(() => {
        cart.forEach((item, index) => {
            const remainingTime = Math.max(0, Math.floor((RESERVATION_DURATION - (Date.now() - item.reservationTime)) / 1000));
            const minutes = Math.floor(remainingTime / 60);
            const seconds = remainingTime % 60;
            const timeLeft = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
            const timeElement = document.getElementById(`time-${index}`);
            if (timeElement) {
                timeElement.textContent = timeLeft;
            }
        });
        validateCart(matches);
    }, 1000);
}


// edit_admin.html
function validateForm() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const usernameRegex = /^[a-zA-Z0-9_-]+$/;
    const passwordRegex = /^(?=.*[A-Z])(?=.*[!@#$%^&*()_+\-=\[\]{}|;:,.<>?])[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{}|;:,.<>?]{8,}$/;

    if (!usernameRegex.test(username)) {
        alert('Имя пользователя должно содержать только латинские буквы, цифры, подчеркивания или дефисы.');
        return false;
    }
    if (password && !passwordRegex.test(password)) {
        alert('Пароль должен быть не короче 8 символов, содержать минимум одну заглавную латинскую букву и один специальный символ.');
        return false;
    }
    return true;
}


// edit_match.html
var gk_isXlsx = false;
var gk_xlsxFileLookup = {};
var gk_fileData = {};
function filledCell(cell) {
    return cell !== '' && cell != null;
}
function loadFileData(filename) {
    if (gk_isXlsx && gk_xlsxFileLookup[filename]) {
        try {
            var workbook = XLSX.read(gk_fileData[filename], { type: 'base64' });
            var firstSheetName = workbook.SheetNames[0];
            var worksheet = workbook.Sheets[firstSheetName];
            var jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1, blankrows: false, defval: '' });
            var filteredData = jsonData.filter(row => row.some(filledCell));
            var headerRowIndex = filteredData.findIndex((row, index) =>
                row.filter(filledCell).length >= filteredData[index + 1]?.filter(filledCell).length
            );
            if (headerRowIndex === -1 || headerRowIndex > 25) {
                headerRowIndex = 0;
            }
            var csv = XLSX.utils.aoa_to_sheet(filteredData.slice(headerRowIndex));
            csv = XLSX.utils.sheet_to_csv(csv, { header: 1 });
            return csv;
        } catch (e) {
            console.error(e);
            return "";
        }
    }
    return gk_fileData[filename] || "";
}

var pendingSeatChanges = {};
var totalSeats = 0;

function toggleSection(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        if (element.classList.contains('active')) {
            element.classList.remove('active');
        } else {
            element.classList.add('active');
        }
        saveToggleState();
    } else {
        console.error('Element not found for ID:', elementId);
    }
}

async function updateSectorPrice(matchSlug, sectorName, formId) {
    const form = document.getElementById(formId);
    const priceInput = form.querySelector('input[name="price"]');
    const newPrice = priceInput.value;
    if (!newPrice || isNaN(newPrice) || newPrice <= 0) {
        alert("Пожалуйста, введите корректную цену (положительное число).");
        return;
    }
    try {
        const response = await fetch(`/admin-panel/edit_sector/${matchSlug}/${sectorName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `price=${newPrice}`
        });
        if (response.ok) {
            alert("Цена сектора успешно обновлена!");
        } else {
            const errorText = await response.text();
            alert(`Ошибка при обновлении цены: ${errorText}`);
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert("Произошла ошибка при обновлении цены.");
    }
}

function updateAvailableSeats(sectorId) {
    const seats = document.querySelectorAll(`#sector-${sectorId} .seat-status`);
    let availableCount = 0;
    seats.forEach(seat => {
        const seatNumber = seat.closest('li')?.querySelector('.seat-item')?.getAttribute('data-number') ||
                        seat.closest('.seat-item')?.getAttribute('data-number');
        const isPendingOccupied = pendingSeatChanges[sectorId]?.[seatNumber] === 'occupied';
        const isPendingAvailable = pendingSeatChanges[sectorId]?.[seatNumber] === 'available';
        if (isPendingAvailable || (!isPendingOccupied && seat.textContent === 'Свободно')) {
            availableCount++;
        }
    });
    const headerElement = document.getElementById(`sector-header-${sectorId}`);
    headerElement.textContent = `Сектор ${sectorId}. Свободно: ${availableCount} шт.`;
    updateTotalSeats();
}

function updateTotalSeats() {
    let totalAvailable = 0;
    document.querySelectorAll('.sector-seats').forEach(sector => {
        const sectorId = JSON.parse(sector.getAttribute('data-sector')).sectorName;
        const seats = document.querySelectorAll(`#sector-${sectorId} .seat-status`);
        seats.forEach(seat => {
            const seatNumber = seat.closest('li')?.querySelector('.seat-item')?.getAttribute('data-number') ||
                            seat.closest('.seat-item')?.getAttribute('data-number');
            const isPendingOccupied = pendingSeatChanges[sectorId]?.[seatNumber] === 'occupied';
            const isPendingAvailable = pendingSeatChanges[sectorId]?.[seatNumber] === 'available';
            if (isPendingAvailable || (!isPendingOccupied && seat.textContent === 'Свободно')) {
                totalAvailable++;
            }
        });
    });
    totalSeats = totalAvailable;
    const totalSeatsInput = document.getElementById('total_seats');
    if (totalSeatsInput) {
        totalSeatsInput.value = totalSeats;
    }
}

function toggleSeatStatus(matchSlug, sectorName, seatNumber, action, buttonElement) {
    const statusSpan = buttonElement.closest('li').querySelector('.seat-status');
    const liElement = buttonElement.closest('li');
    const currentStatus = statusSpan.textContent === 'Свободно' ? 'available' : 'occupied';
    if (!pendingSeatChanges[sectorName]) {
        pendingSeatChanges[sectorName] = {};
    }
    if (!pendingSeatChanges[sectorName][seatNumber]?.originalStatus) {
        pendingSeatChanges[sectorName][seatNumber] = {
            originalStatus: currentStatus,
            status: currentStatus
        };
    }
    const newStatus = action === 'deactivate' ? 'occupied' : 'available';
    pendingSeatChanges[sectorName][seatNumber].status = newStatus;
    if (pendingSeatChanges[sectorName][seatNumber].status === pendingSeatChanges[sectorName][seatNumber].originalStatus) {
        delete pendingSeatChanges[sectorName][seatNumber];
        liElement.classList.remove('pending-change');
        if (Object.keys(pendingSeatChanges[sectorName]).length === 0) {
            delete pendingSeatChanges[sectorName];
        }
    } else {
        liElement.classList.add('pending-change');
    }
    if (action === 'deactivate') {
        statusSpan.textContent = 'Занято';
        buttonElement.textContent = 'Активировать';
        buttonElement.classList.remove('text-red-500');
        buttonElement.classList.add('text-green-500');
        buttonElement.onclick = () => toggleSeatStatus(matchSlug, sectorName, seatNumber, 'activate', buttonElement);
    } else {
        statusSpan.textContent = 'Свободно';
        buttonElement.textContent = 'Деактивировать';
        buttonElement.classList.remove('text-green-500');
        buttonElement.classList.add('text-red-500');
        buttonElement.onclick = () => toggleSeatStatus(matchSlug, sectorName, seatNumber, 'deactivate', buttonElement);
    }
    updateAvailableSeats(sectorName);
}

function saveToggleState() {
    const openSections = [];
    document.querySelectorAll('.toggle-content').forEach((section) => {
        if (section.classList.contains('active')) {
            openSections.push(section.id);
        }
    });
    localStorage.setItem('openSections', JSON.stringify(openSections));
}

function restoreToggleState() {
    const openSections = JSON.parse(localStorage.getItem('openSections') || '[]');
    openSections.forEach((sectionId) => {
        const section = document.getElementById(sectionId);
        if (section) {
            section.classList.add('active');
        }
    });
}

function groupSeatsByRows() {
    const seatsPerRow = 35;
    document.querySelectorAll('.sector-seats').forEach(sector => {
        const sectorData = JSON.parse(sector.getAttribute('data-sector'));
        const sectorId = sectorData.sectorName;
        const matchSlug = sectorData.matchId;
        const sectorPrice = parseInt(sector.getAttribute('data-price'));
        const seats = Array.from(sector.querySelectorAll('.seat-item')).map(seat => ({
            number: parseInt(seat.getAttribute('data-number')),
            available: seat.getAttribute('data-available') === 'true' || seat.getAttribute('data-available') === 'True',
            deleteUrl: seat.getAttribute('data-delete-url'),
            price: seat.getAttribute('data-price') ? Number(seat.getAttribute('data-price')) : 0,
            originalPrice: seat.getAttribute('data-price') ? Number(seat.getAttribute('data-price')) : 0
        }));
        const rows = {};
        seats.forEach(seat => {
            const rowNumber = Math.floor((seat.number - 1) / seatsPerRow) + 1;
            if (!rows[rowNumber]) {
                rows[rowNumber] = [];
            }
            rows[rowNumber].push(seat);
        });
        const rowsContainer = document.createElement('div');
        for (const rowNumber in rows) {
            const localSeats = rows[rowNumber].map(seat => ({
                ...seat,
                localNumber: (seat.number - 1) % seatsPerRow + 1
            }));
            const rowId = `row-${sectorId}-${rowNumber}`;
            const rowDiv = document.createElement('div');
            rowDiv.className = 'ml-4 mt-2 row-container';
            rowDiv.innerHTML = `
                <p class="cursor-pointer" onclick="toggleSection('${rowId}')">
                    Ряд ${rowNumber}
                </p>
                <div id="${rowId}" class="toggle-content">
                    <ul class="ml-4 mt-2">
                        ${localSeats.map(seat => `
                            <li class="flex justify-between items-center py-1">
                                <span>Место ${seat.localNumber}: <span class="seat-status">${seat.available ? 'Свободно' : 'Занято'}</span> <span class="seat-price">${typeof seat.price !== 'undefined' && seat.price !== null ? seat.price : 0} ₽</span></span>
                                <div class="flex items-center space-x-2">
                                    <button onclick="startEditSeatPrice(this, '${sectorId}', ${seat.number}, ${seat.originalPrice})" class="text-blue-500 hover:underline mx-1">Изменить цену</button>
                                    <button onclick="toggleSeatStatus('${matchSlug}', '${sectorId}', ${seat.number}, '${seat.available ? 'deactivate' : 'activate'}', this)" class="${seat.available ? 'text-red-500' : 'text-green-500'} hover:underline">${seat.available ? 'Деактивировать' : 'Активировать'}</button>
                                    <a href="/admin-panel/deactivate_seat/${matchSlug}/${sectorId}/${seat.number}" class="text-red-500 hover:underline">Удалить</a>
                                </div>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `;
            rowsContainer.appendChild(rowDiv);
        }
        sector.replaceWith(rowsContainer);
    });
    restoreToggleState();
    updateTotalSeats();
}

function startEditSeatPrice(button, sectorId, seatNumber, currentPrice) {
    const li = button.closest('li');
    const priceSpan = li.querySelector('.seat-price');
    button.style.display = 'none';
    const input = document.createElement('input');
    input.type = 'number';
    input.value = currentPrice;
    input.min = 1;
    input.className = 'border rounded p-1 w-20 mx-2';
    input.style.width = '70px';
    const okBtn = document.createElement('button');
    okBtn.textContent = 'Ок';
    okBtn.className = 'text-green-500 hover:underline mx-1';
    okBtn.onclick = function() {
        const newPrice = Number(input.value.trim());
        if (!newPrice || isNaN(newPrice) || newPrice <= 0) {
            alert('Пожалуйста, введите корректную цену (положительное число).');
            return;
        }
        if (!pendingSeatChanges[sectorId]) pendingSeatChanges[sectorId] = {};
        if (!pendingSeatChanges[sectorId][seatNumber]) pendingSeatChanges[sectorId][seatNumber] = {};
        const statusSpan = li.querySelector('.seat-status');
        const currentStatus = statusSpan.textContent === 'Свободно' ? 'available' : 'occupied';
        pendingSeatChanges[sectorId][seatNumber].price = newPrice;
        pendingSeatChanges[sectorId][seatNumber].status = currentStatus;
        li.classList.add('pending-change');
        priceSpan.textContent = newPrice + ' ₽';
        input.remove();
        okBtn.remove();
        button.style.display = '';
    };
    priceSpan.parentNode.appendChild(input);
    priceSpan.parentNode.appendChild(okBtn);
    input.focus();
}

function editMatchOnLoad() {
    groupSeatsByRows();
    document.getElementById('edit-match-form').addEventListener('submit', async function(event) {
        event.preventDefault();
        const formData = new FormData(this);
        try {
            const formResponse = await fetch(this.action, {
                method: 'POST',
                body: formData
            });
            if (!formResponse.ok) {
                const errorText = await formResponse.text();
                alert(`Ошибка при сохранении матча: ${errorText}`);
                return;
            }
            if (Object.keys(pendingSeatChanges).length > 0) {
                const matchSlug = this.action.split('/').pop();
                const payload = {
                    seat_changes: pendingSeatChanges,
                    total_seats: totalSeats
                };
                const response = await fetch(`/admin-panel/update_seats/${matchSlug}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload)
                });
                if (response.ok) {
                    alert('Изменения успешно сохранены!');
                    pendingSeatChanges = {};
                    document.querySelectorAll('.pending-change').forEach(el => el.classList.remove('pending-change'));
                    document.querySelectorAll('.sector-seats').forEach(sector => {
                        updateAvailableSeats(JSON.parse(sector.getAttribute('data-sector')).sectorName);
                    });
                } else {
                    const errorText = await response.text();
                    alert(`Ошибка при сохранении статусов мест: ${errorText}`);
                }
            } else {
                alert('Матч успешно сохранен!');
            }
        } catch (error) {
            console.error('Ошибка:', error);
            alert('Произошла ошибка при сохранении.');
        }
    });
}

// index.html
function toggleFAQ(id) {
    const element = document.getElementById(id);
    const arrow = element.previousElementSibling.querySelector('svg');
    if (element.classList.contains('hidden')) {
        element.classList.remove('hidden');
        arrow.classList.add('rotate-180');
    } else {
        element.classList.add('hidden');
        arrow.classList.remove('rotate-180');
    }
}

function indexOnLoad() {
    updateCartCount();
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('success') === 'true') {
        alert('Заявка успешно отправлена!');
        // Удаляем параметр success из URL
        urlParams.delete('success');
        const newUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '');
        window.history.replaceState({}, document.title, newUrl);
    }
}

// matches.html
function matchesOnLoad() {
    updateCartCount();
    filterMatches();
}

function notFoundOnLoad() {
    updateCartCount();
}

function isSeatAvailable(row, seat) {
    return (window.availableSeats || []).some(function(s) { return s.row == row && s.seat == seat; });
}

function isSeatInCart(row, seat, sectorName) {
    const cartSeats = JSON.parse(localStorage.getItem('cart')) || [];
    return cartSeats.some(function(s) { return s.row == row && s.seat == seat && s.sector_name == sectorName; });
}

function updateSVGSeatsAndLabels() {
    // Переместить rect в конец группы
    document.querySelectorAll('#svg-container g').forEach(function(g) {
        const rects = g.querySelectorAll('rect[data-row][data-seat]');
        rects.forEach(function(rect) {
            g.appendChild(rect);
        });
    });
    // Удалить все старые подписи
    document.querySelectorAll('#svg-container text.svg-seat-label').forEach(function(label) {
        label.remove();
    });
    // Добавить подписи для всех доступных мест
    document.querySelectorAll('#svg-container rect[data-row][data-seat]').forEach(function(rect) {
        const row = parseInt(rect.getAttribute('data-row'));
        const seat = parseInt(rect.getAttribute('data-seat'));
        if (isSeatAvailable(row, seat)) {
            const x = parseFloat(rect.getAttribute('x')) + parseFloat(rect.getAttribute('width')) / 2;
            const y = parseFloat(rect.getAttribute('y')) + parseFloat(rect.getAttribute('height')) / 2;
            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            label.setAttribute('x', x);
            label.setAttribute('y', y);
            label.setAttribute('data-row', row);
            label.setAttribute('data-seat', seat);
            label.setAttribute('class', 'svg-seat-label');
            label.textContent = seat;
            rect.parentNode.appendChild(label);
        }
    });
    // Подсветка и обработчики клика
    document.querySelectorAll('#svg-container rect[data-row][data-seat]').forEach(function(rect) {
        const row = parseInt(rect.getAttribute('data-row'));
        const seat = parseInt(rect.getAttribute('data-seat'));
        var seatInfo = (window.availableSeats || []).find(function(s) { return s.row == row && s.seat == seat; });
        var price = seatInfo ? seatInfo.price : 0;
        var match_id = seatInfo ? seatInfo.match_id : (window.matchId || '');
        var sector_name = seatInfo ? seatInfo.sector_name : (window.sectorName || '');
        // Удаляем все старые обработчики клика (cloneNode)
        const newRect = rect.cloneNode(true);
        rect.parentNode.replaceChild(newRect, rect);
    });
    // Повторно навешиваем обработчики клика и обновляем цвета
    document.querySelectorAll('#svg-container rect[data-row][data-seat]').forEach(function(rect) {
        const row = parseInt(rect.getAttribute('data-row'));
        const seat = parseInt(rect.getAttribute('data-seat'));
        var seatInfo = (window.availableSeats || []).find(function(s) { return s.row == row && s.seat == seat; });
        var price = seatInfo ? seatInfo.price : 0;
        var match_id = seatInfo ? seatInfo.match_id : (window.matchId || '');
        var sector_name = seatInfo ? seatInfo.sector_name : (window.sectorName || '');
        if (isSeatInCart(row, seat, sector_name)) {
            rect.style.fill = '#d1aaff';
            rect.style.stroke = '#4B006E';
            rect.style.cursor = 'pointer';
        } else if (isSeatAvailable(row, seat)) {
            rect.style.fill = '#ae6ceb';
            rect.style.stroke = '#4B006E';
            rect.style.cursor = 'pointer';
        } else {
            rect.style.fill = '#d1d5db';
            rect.style.stroke = '#bbb';
            rect.style.cursor = 'not-allowed';
        }
        rect.addEventListener('click', function() {
            if (isSeatAvailable(row, seat)) {
                let cartSeats = JSON.parse(localStorage.getItem('cart')) || [];
                if (isSeatInCart(row, seat, sector_name)) {
                    // Удалить из корзины
                    cartSeats = cartSeats.filter(function(s) {
                        return !(s.row == row && s.seat == seat && s.sector_name == sector_name && s.match_id == match_id);
                    });
                    localStorage.setItem('cart', JSON.stringify(cartSeats));
                    updateSVGSeatsAndLabels();
                    updateCartCount();
                } else {
                    // Добавить в корзину
                    cartSeats.push({
                        row: row,
                        seat: seat,
                        price: price,
                        sector_name: sector_name,
                        match_id: match_id,
                        reservationTime: Date.now()
                    });
                    localStorage.setItem('cart', JSON.stringify(cartSeats));
                    updateSVGSeatsAndLabels();
                    updateCartCount();
                    showNotification('Место добавлено в корзину!');
                }
            }
        });
    });
    updateCartCount();
    document.querySelectorAll('#svg-container rect[data-row][data-seat]').forEach(function(rect) {
        rect.onmousemove = function(e) {
            const row = rect.getAttribute('data-row');
            const seat = rect.getAttribute('data-seat');
            const seatInfo = (window.availableSeats || []).find(s => s.row == row && s.seat == seat);
            if (!seatInfo) return;
            const tooltip = document.getElementById('seat-tooltip');
            tooltip.querySelector('.sector-name').textContent = `Сектор ${(window.sectorName || '')}`;
            tooltip.querySelector('#tooltip-row').textContent = row;
            tooltip.querySelector('#tooltip-seat').textContent = seat;
            tooltip.querySelector('#tooltip-price').textContent = seatInfo.price;
            tooltip.style.display = 'block';
            const tooltipRect = tooltip.getBoundingClientRect();
            let left = e.pageX - tooltipRect.width / 2;
            let top = e.pageY - tooltipRect.height - 12;
            if (left < 0) left = 10;
            if (left + tooltipRect.width > window.innerWidth) left = window.innerWidth - tooltipRect.width - 10;
            if (top < 0) top = e.pageY + 12;
            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        };
        rect.onmouseleave = function() {
            const tooltip = document.getElementById('seat-tooltip');
            tooltip.style.display = 'none';
        };
    });
}

function formatDate(dateString, timeString) {
    const months = [
        'Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
        'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря'
    ];
    const date = new Date(dateString + (timeString ? 'T' + timeString : ''));
    const day = date.getDate();
    const month = months[date.getMonth()];
    const year = date.getFullYear();
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${day} ${month} ${year}, ${hours}:${minutes}`;
}

function sectorViewOnLoad() {
    updateSVGSeatsAndLabels();
    // форматирование даты, если нужно
    const dateElem = document.getElementById('match-date');
    if (dateElem && window.matchDate && window.matchTime) {
        dateElem.textContent = formatDate(window.matchDate, window.matchTime);
    }
    // восстановление открытого ряда
    const openRow = localStorage.getItem('openRow');
    if (openRow) {
        const content = document.getElementById(`row-${openRow}`);
        if (content) {
            content.classList.add('open');
        }
    }
}

function deleteAdmin(adminId, role) {
    if (role === 'superadmin') {
        alert('Нельзя удалить superadmin.');
        return;
    }
    if (!confirm('Вы уверены, что хотите удалить этого администратора?')) {
        return;
    }
    fetch(`/admin-panel/set-admin/delete/${adminId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        },
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Ошибка удаления');
        }
        return response;
    })
    .then(() => {
        window.location.reload();
    })
    .catch(error => {
        console.error('Ошибка:', error);
        alert('Не удалось удалить администратора');
    });
}

function selectSector(sectorName) {
    const matchId = window.matchId || '';
    window.location.href = `/sector_view/${matchId}/${sectorName}`;
}

function scrollToStadiumMap() {
    const stadiumMap = document.querySelector('.stadium-map');
    const offset = 100;
    const elementPosition = stadiumMap.getBoundingClientRect().top + window.scrollY;
    const offsetPosition = elementPosition - offset;
    window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
    });
}

function ticketsFormatDate(dateString, timeString) {
    const months = [
        'Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
        'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря'
    ];
    const date = new Date(dateString + 'T' + (timeString || '00:00'));
    const day = date.getDate();
    const month = months[date.getMonth()];
    const year = date.getFullYear();
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${day} ${month} ${year}, ${hours}:${minutes}`;
}

function toggleTickets() {
    const ticketsSection = document.querySelector('.tickets-section');
    ticketsSection.classList.toggle('active');
}

function getAvailableSeats(sectorName) {
    const sector = (window.matchSectors || []).find(s => s.name === sectorName);
    if (sector && sector.seats) {
        return sector.seats.filter(seat => seat.available).length;
    }
    return 0;
}

function getSectorPriceRange(sectorName) {
    const sector = (window.matchSectors || []).find(s => s.name === sectorName);
    if (sector && sector.seats) {
        const prices = sector.seats.filter(seat => seat.available).map(seat => seat.price);
        if (prices.length > 0) {
            return {min: Math.min(...prices), max: Math.max(...prices)};
        }
    }
    return {min: 0, max: 0};
}

function initSectorFiltersAndTooltip() {
    const tooltip = document.getElementById('sector-tooltip');
    const sectors = document.querySelectorAll('.sector.active');
    const filterButtons = document.querySelectorAll('.price-filter');
    let activeFilter = null;

    sectors.forEach(sector => {
        const sectorName = sector.getAttribute('data-id');

        sector.addEventListener('mouseover', function (e) {
            const availableSeats = getAvailableSeats(sectorName);
            const priceRange = getSectorPriceRange(sectorName);

            tooltip.querySelector('.sector-name').textContent = `Сектор ${sectorName}`;
            tooltip.querySelector('#available-seats').textContent = availableSeats;
            if (priceRange.min === priceRange.max) {
                tooltip.querySelector('#sector-price').textContent = priceRange.min;
            } else {
                tooltip.querySelector('#sector-price').textContent = priceRange.min + '–' + priceRange.max;
            }

            tooltip.style.display = 'block';
            tooltip.style.left = e.pageX + 10 + 'px';
            tooltip.style.top = e.pageY + 10 + 'px';
        });

        sector.addEventListener('mousemove', function (e) {
            const tooltipWidth = tooltip.offsetWidth;
            const tooltipHeight = tooltip.offsetHeight;
            const windowWidth = window.innerWidth;
            const windowHeight = window.innerHeight;

            let left = e.pageX + 10;
            let top = e.pageY + 10;

            if (left + tooltipWidth > windowWidth) {
                left = e.pageX - tooltipWidth - 10;
            }

            if (top + tooltipHeight > windowHeight) {
                top = e.pageY - tooltipHeight - 10;
            }

            if (left < 0) {
                left = 10;
            }

            if (top < 0) {
                top = 10;
            }

            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        });

        sector.addEventListener('mouseout', function () {
            tooltip.style.display = 'none';
        });
    });

    function applySectorHighlight(minPrice, maxPrice, isPreview = false) {
        sectors.forEach(sector => {
            const sectorName = sector.getAttribute('data-id');
            const price = getSectorPriceRange(sectorName);

            if (price.min >= minPrice && price.max <= maxPrice) {
                sector.classList.remove('dimmed');
                sector.classList.add('highlighted');
            } else if (isPreview) {
                sector.classList.add('dimmed');
                sector.classList.remove('highlighted');
            }
        });
    }

    function restoreSectorState() {
        sectors.forEach(sector => {
            const sectorName = sector.getAttribute('data-id');
            const price = getSectorPriceRange(sectorName);

            if (activeFilter) {
                const minPrice = parseInt(activeFilter.getAttribute('data-min'));
                const maxPrice = parseInt(activeFilter.getAttribute('data-max'));
                if (price.min >= minPrice && price.max <= maxPrice) {
                    sector.classList.remove('dimmed');
                    sector.classList.add('highlighted');
                } else {
                    sector.classList.add('dimmed');
                    sector.classList.remove('highlighted');
                }
            } else {
                sector.classList.remove('dimmed', 'highlighted');
            }
        });

        // Восстанавливаем состояние кнопок
        filterButtons.forEach(btn => {
            if (activeFilter && btn !== activeFilter) {
                btn.classList.add('dimmed');
            } else {
                btn.classList.remove('dimmed');
            }
        });
    }

    filterButtons.forEach(button => {
        button.addEventListener('click', function () {
            const minPrice = parseInt(button.getAttribute('data-min'));
            const maxPrice = parseInt(button.getAttribute('data-max'));

            if (activeFilter === button) {
                sectors.forEach(sector => {
                    sector.classList.remove('dimmed', 'highlighted');
                });
                filterButtons.forEach(btn => {
                    btn.classList.remove('dimmed');
                });
                activeFilter.classList.remove('active');
                activeFilter = null;
                return;
            }

            if (activeFilter) {
                activeFilter.classList.remove('active');
            }

            button.classList.add('active');
            activeFilter = button;

            applySectorHighlight(minPrice, maxPrice);

            filterButtons.forEach(btn => {
                if (btn !== activeFilter) {
                    btn.classList.add('dimmed');
                } else {
                    btn.classList.remove('dimmed');
                }
            });
        });

        button.addEventListener('mouseover', function () {
            const minPrice = parseInt(button.getAttribute('data-min'));
            const maxPrice = parseInt(button.getAttribute('data-max'));
            applySectorHighlight(minPrice, maxPrice, true);
            filterButtons.forEach(btn => {
                if (btn !== button) {
                    btn.classList.add('dimmed');
                } else {
                    btn.classList.remove('dimmed');
                }
            });
        });

        button.addEventListener('mouseout', function () {
            restoreSectorState();
        });
    });
}

function ticketsOnLoad() {
    updateCartCount();
    const dateElement = document.querySelector('.match-info .date');
    if (dateElement && window.matchDate && window.matchTime) {
        dateElement.textContent = ticketsFormatDate(window.matchDate, window.matchTime);
    }
    if (window.matchSectors) {
        initSectorFiltersAndTooltip();
    }
}

