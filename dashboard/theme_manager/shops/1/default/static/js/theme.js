// Modern Theme JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Initialize theme functionality
    initializeCart();
    initializeProductInteractions();
    initializeNavigation();
    initializeAnimations();
});

// Cart functionality
function initializeCart() {
    const cartButtons = document.querySelectorAll('[data-add-to-cart]');
    const cartBadge = document.querySelector('.cart-badge');
    
    cartButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const productId = this.dataset.productId;
            const productName = this.dataset.productName;
            
            // Add loading state
            const originalText = this.textContent;
            this.textContent = 'Adding...';
            this.disabled = true;
            
            // Simulate API call
            setTimeout(() => {
                addToCart(productId, productName);
                this.textContent = 'Added!';
                
                setTimeout(() => {
                    this.textContent = originalText;
                    this.disabled = false;
                }, 1000);
            }, 500);
        });
    });
}

function addToCart(productId, productName) {
    // Get current cart from localStorage
    let cart = JSON.parse(localStorage.getItem('cart') || '[]');
    
    // Check if product already exists
    const existingItem = cart.find(item => item.id === productId);
    
    if (existingItem) {
        existingItem.quantity += 1;
    } else {
        cart.push({
            id: productId,
            name: productName,
            quantity: 1
        });
    }
    
    // Save to localStorage
    localStorage.setItem('cart', JSON.stringify(cart));
    
    // Update cart badge
    updateCartBadge();
    
    // Show notification
    showNotification(`${productName} added to cart!`);
}

function updateCartBadge() {
    const cart = JSON.parse(localStorage.getItem('cart') || '[]');
    const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
    
    const badge = document.querySelector('.cart-badge');
    if (badge) {
        badge.textContent = totalItems;
        badge.style.display = totalItems > 0 ? 'flex' : 'none';
    }
}

// Product interactions
function initializeProductInteractions() {
    // Product image hover effects
    const productImages = document.querySelectorAll('.product-image');
    
    productImages.forEach(img => {
        img.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.05)';
        });
        
        img.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });
    
    // Quick view functionality
    const quickViewButtons = document.querySelectorAll('[data-quick-view]');
    
    quickViewButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const productId = this.dataset.productId;
            openQuickView(productId);
        });
    });
}

function openQuickView(productId) {
    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4';
    
    // Create modal content
    const modal = document.createElement('div');
    modal.className = 'bg-white rounded-lg max-w-2xl w-full max-h-full overflow-y-auto';
    modal.innerHTML = `
        <div class="p-6">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-xl font-semibold">Quick View</h3>
                <button class="text-gray-400 hover:text-gray-600" onclick="closeQuickView()">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <div class="text-center py-8">
                <div class="loading mx-auto mb-4"></div>
                <p>Loading product details...</p>
            </div>
        </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Close on overlay click
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            closeQuickView();
        }
    });
}

function closeQuickView() {
    const overlay = document.querySelector('.fixed.inset-0.bg-black');
    if (overlay) {
        overlay.remove();
    }
}

// Navigation
function initializeNavigation() {
    // Mobile menu toggle
    const mobileMenuButton = document.querySelector('[data-mobile-menu]');
    const mobileMenu = document.querySelector('.mobile-menu');
    
    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener('click', function() {
            mobileMenu.classList.toggle('hidden');
        });
    }
    
    // Search functionality
    const searchInput = document.querySelector('[data-search]');
    
    if (searchInput) {
        let searchTimeout;
        
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            
            searchTimeout = setTimeout(() => {
                const query = this.value.trim();
                if (query.length > 2) {
                    performSearch(query);
                }
            }, 300);
        });
    }
}

function performSearch(query) {
    // Implement search functionality
    console.log('Searching for:', query);
}

// Animations
function initializeAnimations() {
    // Intersection Observer for fade-in animations
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('fade-in');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    // Observe elements for animation
    const animateElements = document.querySelectorAll('.product-card, .category-card, .feature-card');
    animateElements.forEach(el => observer.observe(el));
}

// Notifications
function showNotification(message, type = 'success') {
    // Remove existing notifications
    const existing = document.querySelector('.notification');
    if (existing) {
        existing.remove();
    }
    
    // Create notification
    const notification = document.createElement('div');
    notification.className = `notification fixed top-4 right-4 z-50 px-6 py-3 rounded-lg shadow-lg text-white ${
        type === 'success' ? 'bg-green-500' : 'bg-red-500'
    }`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Utility functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Initialize cart badge on page load
updateCartBadge();