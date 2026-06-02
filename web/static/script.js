let updateInterval = null;

async function fetchParkingStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error('Error fetching status:', error);
    }
}

function updateDashboard(data) {
    document.getElementById('totalCars').textContent = data.total_cars_today;
    document.getElementById('freeSlots').textContent = data.free_slots;
    
    const occupancyRate = ((data.occupied_slots / data.total_slots) * 100).toFixed(1);
    document.getElementById('occupancyRate').textContent = `${occupancyRate}%`;
    

    const slotsContainer = document.getElementById('slotsContainer');
    slotsContainer.innerHTML = '';
    
    data.slots.forEach(slot => {
        const slotCard = document.createElement('div');
        slotCard.className = `slot-card ${slot.occupied ? 'occupied' : 'free'}`;
        
        slotCard.innerHTML = `
            <div class="slot-number">Slot ${slot.id}</div>
            <div class="slot-status">
                <span class="status-dot ${slot.occupied ? 'occupied' : 'free'}"></span>
                <span>${slot.occupied ? 'Occupied' : 'Free'}</span>
            </div>
        `;
        
        slotsContainer.appendChild(slotCard);
    });

    animateUpdate();
}

function animateUpdate() {
    const stats = document.querySelectorAll('.stat-value');
    stats.forEach(stat => {
        stat.style.transform = 'scale(1.1)';
        setTimeout(() => {
            stat.style.transform = 'scale(1)';
        }, 200);
    });
}

async function resetCounter() {
    if (confirm('Reset daily car counter?')) {
        try {
            const response = await fetch('/api/reset');
            const data = await response.json();
            if (data.message) {
                fetchParkingStatus(); 
            }
        } catch (error) {
            console.error('Error resetting counter:', error);
        }
    }
}

function initDashboard() {
    fetchParkingStatus();
    updateInterval = setInterval(fetchParkingStatus, 2000); 
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'r' || e.key === 'R') {
        resetCounter();
    }
});

document.addEventListener('DOMContentLoaded', initDashboard);

window.addEventListener('beforeunload', () => {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
});