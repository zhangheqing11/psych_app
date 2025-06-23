const ClientPortal = ({ user, allData, onLogout, onSave, showAlert }) => {
        const { useState, useMemo, useEffect } = React;
        const [isEditing, setIsEditing] = useState(false);
        const [clientProfile, setClientProfile] = useState(null);

        useEffect(() => {
            // BUG FIX: Check if allData.clients is specifically an array.
            // This prevents errors if it receives data meant for another role (e.g., counselor data).
            if (allData && Array.isArray(allData.clients)) {
                const profile = allData.clients.find(c => c.username === user.username);
                setClientProfile(profile);
            }
        }, [allData, user.username]);

        // ... rest of the component is unchanged ...

        if (!clientProfile) {
            return <div className="min-h-screen flex items-center justify-center">正在加载您的信息...</div>;
        }

        // ... JSX for the portal ...
    };
