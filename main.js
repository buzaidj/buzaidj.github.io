const ENDPOINT = 'https://api.jamesbuzaid.com/browsing';

function timeAgo(date) {
    const now = new Date();
    const diff = Math.abs(now - date) / 1000; // Calculate the difference in seconds

    if (diff < 60) {
        // Less than a minute ago
        const seconds = Math.floor(diff);
        return `Now`;
    } else if (diff < 3600) {
        // Less than an hour ago
        const minutes = Math.floor(diff / 60);
        return `${minutes}m ago`;
    } else if (diff < 86400) {
        // Less than a day ago
        const hours = Math.floor(diff / 3600);
        return `${hours}h ago`;
    } else {
        // More than a day ago
        const days = Math.floor(diff / 86400);
        return `${days}d ago`;
    }
}

function makeFetchRequest(callback) {
    fetch(ENDPOINT)
        .then(response => response.json())
        .then(data => callback(data))
        .catch(err => {
            console.error('An error occurred: ', err);
        });
}

function processData(data) {
    let history = [];

    if (data.liveTab) {
        history.push(data.liveTab);
    }
    history = history.concat(data.recentBrowsing.slice(0, 10));

    history.sort((a, b) => new Date(b.activeTime) - new Date(a.activeTime));

    return history.map(x => {
        return {
            title: x.tabInfo.title,
            url: x.url,
            favIconUrl: x.tabInfo.favIconUrl,
            timeAgo: timeAgo(new Date(x.activeTime)),
            numTimesSeen: x.numTimesSeen,
        }
    })
}

function sliceUrl(url) {
    if (url.length >= 45) {
        return url.slice(0, 45) + '...'
    }
    else {
        return url;
    }
}

function sliceTitle(title) {
    if (title.length >= 40) {
        return title.slice(0, 40) + '...'
    }
    else {
        return title;
    }
}

function createElementsFromProcessedData(data) {
    const browsingBox = document.getElementById('browsing-box');
    for (const elem of data) {
        const leftColDiv = document.createElement('div');

        const minsAgo = document.createElement('p');
        minsAgo.className = 'time-ago-p'
        minsAgo.textContent = elem.timeAgo;
        leftColDiv.appendChild(minsAgo);

        const rightColDiv = document.createElement('div');

        const browsingCardDiv = document.createElement('div');
        browsingCardDiv.className = 'browsing-card';

        if (elem.favIconUrl) {
            const img = document.createElement('img');
            img.style.width = '16px';
            img.style.height = '16px';
            img.style.marginRight = '2px';
            img.src = elem.favIconUrl;
            img.alt = '';

            browsingCardDiv.appendChild(img);
        }

        const browsingCardNameUrl = document.createElement('div');
        browsingCardNameUrl.className = 'browsing-card-name-url';

        const browsingCardName = document.createElement('p');
        browsingCardName.className = 'browsing-card-name';
        browsingCardName.textContent = sliceTitle(elem.title);
        browsingCardNameUrl.appendChild(browsingCardName);

        const browsingCardUrl = document.createElement('a');
        browsingCardUrl.className = 'browsing-card-url';
        browsingCardUrl.textContent = sliceUrl(elem.url);
        browsingCardUrl.href = elem.url;
        browsingCardNameUrl.appendChild(browsingCardUrl);

        browsingCardDiv.appendChild(browsingCardNameUrl);
        rightColDiv.appendChild(browsingCardDiv);

        browsingBox.appendChild(leftColDiv);
        browsingBox.appendChild(rightColDiv);
    }
}

makeFetchRequest(data => {
    createElementsFromProcessedData(processData(data))
})