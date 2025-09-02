
// Theme management
function initializeTheme() {
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    
    if (!themeToggle) return;
    
    const themeIcon = themeToggle.querySelector('i');
    
    // Load saved theme or default to light
    const savedTheme = localStorage.getItem('theme') || 'light';
    body.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme, themeIcon);

    themeToggle.addEventListener('click', () => {
        const currentTheme = body.getAttribute('data-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';

        body.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(newTheme, themeIcon);
    });
}

function updateThemeIcon(theme, themeIcon) {
    if (themeIcon) {
        themeIcon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
    }
}

// Sidebar management
function initializeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const mainContent = document.getElementById('mainContent');

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', toggleSidebar);
    }
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', closeSidebar);
    }

    function toggleSidebar() {
        if (sidebar) sidebar.classList.toggle('open');
        if (sidebarOverlay) sidebarOverlay.classList.toggle('active');
        if (mainContent) mainContent.classList.toggle('sidebar-open');
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('open');
        if (sidebarOverlay) sidebarOverlay.classList.remove('active');
        if (mainContent) mainContent.classList.remove('sidebar-open');
    }

    // Handle window resize
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 1024) {
            closeSidebar();
        }
    });

    // Expose functions globally for other scripts
    window.toggleSidebar = toggleSidebar;
    window.closeSidebar = closeSidebar;
}

// Modal management
function initializeModals() {
    // Close modals when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
        }
    });

    // Close modals with Escape key
    window.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            const openModals = document.querySelectorAll('.modal[style*="block"]');
            openModals.forEach(modal => {
                modal.style.display = 'none';
            });
        }
    });
}

// Logout functionality
function initializeLogout() {
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                const response = await fetch('/api/logout', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    window.location.href = '/login';
                } else {
                    alert('Logout failed. Please try again.');
                }
            } catch (error) {
                console.error('Error during logout:', error);
                alert('An error occurred during logout.');
            }
        });
    }
}

// File upload handling
function initializeFileUpload() {
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(fileInput => {
        const wrapper = fileInput.closest('.file-input-wrapper');
        if (!wrapper) return;
        
        const fileDisplay = wrapper.querySelector('.file-input-display');
        if (!fileDisplay) return;

        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                fileDisplay.classList.add('has-file');
                const fileIcon = file.name.endsWith('.xlsx') ? 'fa-file-excel' : 'fa-file-csv';
                fileDisplay.innerHTML = `
                    <i class="fas ${fileIcon}"></i>
                    <div>
                        <strong>${file.name}</strong><br>
                        <span>Ready to process (${(file.size / 1024).toFixed(1)} KB)</span>
                    </div>
                `;
            }
        });

        // Drag and drop functionality
        fileDisplay.addEventListener('dragover', function(e) {
            e.preventDefault();
            fileDisplay.classList.add('dragover');
        });

        fileDisplay.addEventListener('dragleave', function(e) {
            e.preventDefault();
            fileDisplay.classList.remove('dragover');
        });

        fileDisplay.addEventListener('drop', function(e) {
            e.preventDefault();
            fileDisplay.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                fileInput.dispatchEvent(new Event('change'));
            }
        });
    });
}

// Utility functions
function formatDuration(seconds) {
    if (!seconds && seconds !== 0) return "0 sec";
    
    const numSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
    
    if (numSeconds === 0) return "0 sec";
    
    const hours = Math.floor(numSeconds / 3600);
    const minutes = Math.floor((numSeconds % 3600) / 60);
    const remainingSeconds = numSeconds % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${remainingSeconds}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${remainingSeconds}s`;
    } else {
        return `${remainingSeconds} sec`;
    }
}

function formatDateTime(dateTimeStr) {
    try {
        if (!dateTimeStr || dateTimeStr === 'null' || dateTimeStr === 'undefined' || dateTimeStr === 'Invalid Date') {
            return 'Invalid Date';
        }
        
        const cleanedStr = String(dateTimeStr).trim();
        
        if (cleanedStr.length < 8) {
            return 'Invalid Date';
        }
        
        if (/^(nan|null|none|invalid|unknown)$/i.test(cleanedStr)) {
            return 'Invalid Date';
        }
        
        const date = new Date(cleanedStr);
        
        if (isNaN(date.getTime())) {
            const dateMatch = cleanedStr.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
            const timeMatch = cleanedStr.match(/(\d{1,2}):(\d{1,2}):(\d{1,2})/);
            
            if (dateMatch) {
                const year = parseInt(dateMatch[1]);
                const month = parseInt(dateMatch[2]) - 1;
                const day = parseInt(dateMatch[3]);
                
                let hour = 0, minute = 0, second = 0;
                if (timeMatch) {
                    hour = parseInt(timeMatch[1]);
                    minute = parseInt(timeMatch[2]);
                    second = parseInt(timeMatch[3]);
                }
                
                if (year >= 1970 && year <= 2100 && month >= 0 && month <= 11 &&
                    day >= 1 && day <= 31 && hour >= 0 && hour <= 23 &&
                    minute >= 0 && minute <= 59 && second >= 0 && second <= 59) {
                    
                    const reconstructedDate = new Date(year, month, day, hour, minute, second);
                    if (!isNaN(reconstructedDate.getTime())) {
                        const options = {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                            hour12: true
                        };
                        return reconstructedDate.toLocaleString('en-US', options);
                    }
                }
            }
            
            const simpleDateMatch = cleanedStr.match(/(\d{4}-\d{1,2}-\d{1,2})/);
            if (simpleDateMatch) {
                return simpleDateMatch[1] + ' (Time unavailable)';
            }
            
            return 'Invalid Date';
        }
        
        const year = date.getFullYear();
        if (year < 1970 || year > 2100) {
            return `Invalid Date (Year: ${year})`;
        }
        
        const options = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        };
        
        return date.toLocaleString('en-US', options);
        
    } catch (error) {
        console.error('Date formatting error:', error, 'Input:', dateTimeStr);
        return 'Invalid Date';
    }
}

// Initialize everything when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeTheme();
    initializeSidebar();
    initializeModals();
    initializeLogout();
    initializeFileUpload();
});

// Expose utility functions globally
window.formatDuration = formatDuration;
window.formatDateTime = formatDateTime;
