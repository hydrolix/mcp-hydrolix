export default {
    content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
    theme: {
        extend: {
            animation: {'fade-in': 'fadeIn 0.3s ease-in-out', 'slide-up': 'slideUp 0.3s ease-out'},
            keyframes: {
                fadeIn: {'0%': {opacity: '0'}, '100%': {opacity: '1'}},
                slideUp: {
                    '0%': {opacity: '0', transform: 'translateY(10px)'},
                    '100%': {opacity: '1', transform: 'translateY(0)'}
                }
            }
        }
    },
    plugins: []
};
