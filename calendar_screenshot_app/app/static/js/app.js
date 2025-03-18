/**
 * Calendar Screenshot Analyzer main JavaScript file
 */

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize clipboard functionality for all copy buttons
    initializeClipboardButtons();
    
    // Add screenshot upload preview functionality if on the right page
    const screenshotUpload = document.querySelector('input[name="screenshot"]');
    if (screenshotUpload) {
        initializeScreenshotPreview(screenshotUpload);
    }
});

/**
 * Initialize clipboard copy functionality
 */
function initializeClipboardButtons() {
    document.querySelectorAll('.copy-btn').forEach(button => {
        button.addEventListener('click', function() {
            const textToCopy = this.getAttribute('data-text');
            
            navigator.clipboard.writeText(textToCopy)
                .then(() => {
                    // Show success feedback
                    const originalText = this.innerHTML;
                    this.innerHTML = '<i class="bi bi-check"></i> Copied!';
                    
                    // Reset after 2 seconds
                    setTimeout(() => {
                        this.innerHTML = originalText;
                    }, 2000);
                })
                .catch(err => {
                    console.error('Could not copy text: ', err);
                    alert('Failed to copy to clipboard');
                });
        });
    });
}

/**
 * Initialize screenshot upload preview
 */
function initializeScreenshotPreview(fileInput) {
    fileInput.addEventListener('change', function() {
        // Find or create preview element
        let previewContainer = document.getElementById('screenshot-preview');
        if (!previewContainer) {
            previewContainer = document.createElement('div');
            previewContainer.id = 'screenshot-preview';
            previewContainer.className = 'mt-3';
            fileInput.parentNode.after(previewContainer);
        }
        
        // Clear existing preview
        previewContainer.innerHTML = '';
        
        // Check if a file was selected
        if (this.files && this.files[0]) {
            const file = this.files[0];
            
            // Only process image files
            if (!file.type.match('image.*')) {
                previewContainer.innerHTML = '<div class="alert alert-warning">Please select an image file</div>';
                return;
            }
            
            // Create a preview
            const reader = new FileReader();
            reader.onload = function(e) {
                const img = document.createElement('img');
                img.src = e.target.result;
                img.className = 'img-fluid thumbnail';
                img.style.maxHeight = '200px';
                img.style.maxWidth = '100%';
                
                previewContainer.appendChild(img);
            };
            
            reader.readAsDataURL(file);
        }
    });
}

/**
 * Fetch and display calendar events
 */
function fetchCalendarEvents(calendarIds, startDate, endDate) {
    // In a real app, this would make an AJAX call to get events
    // For now, we'll just log the request
    console.log('Fetching events for calendars:', calendarIds);
    console.log('Date range:', startDate, 'to', endDate);
    
    // This would be replaced with a real API call
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve([]);
        }, 300);
    });
}

/**
 * Handle screenshot analysis submission
 */
function submitScreenshotForAnalysis(imageData) {
    // This would be replaced with a real API call
    console.log('Submitting screenshot for analysis');
    
    fetch('/screenshot/analyze', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            screenshot_data: imageData
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Analysis results:', data);
        // This would trigger a function to display the results
        if (typeof window.displayAnalysisResults === 'function') {
            window.displayAnalysisResults(data);
        }
    })
    .catch(error => {
        console.error('Error analyzing screenshot:', error);
    });
} 