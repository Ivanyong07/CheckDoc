const API_BASE = "http://127.0.0.1:8000";

let emails = [];
let selectedEmail = null;

document.addEventListener("DOMContentLoaded", () => {
    loadEmails();
    setupCategories();
});

async function loadEmails() {
    const emailList = document.getElementById("email-list");

    try {
        const response = await fetch(`${API_BASE}/emails/`);

        if (!response.ok) {
            throw new Error("Failed to load emails");
        }

        emails = await response.json();

        document.getElementById("email-count").textContent = emails.length;

        renderEmailList(emails);

        addTerminalLog("Emails loaded from database", "success");
    } catch (error) {
        console.error(error);

        emailList.innerHTML = `
            <div class="empty-state">
                Failed to load emails.
            </div>
        `;

        addTerminalLog("Failed to load emails", "error");
    }
}


function renderEmailList(emailData) {
    const emailList = document.getElementById("email-list");

    if (!emailData || emailData.length === 0) {
        emailList.innerHTML = `
            <div class="empty-state">
                No emails found.
            </div>
        `;
        return;
    }

    emailList.innerHTML = emailData.map(email => {
        const originalIndex = emails.findIndex(
            item => item.id === email.id
        );

        const emailNumber =
            `EMAIL_${String(originalIndex + 1).padStart(3, "0")}`;

        const classification = email.classification
            ? formatCategory(email.classification)
            : "Pending";

        return `
            <div
                class="email-item"
                data-email-id="${escapeHtml(email.id)}"
                onclick="selectEmail('${escapeHtml(email.id)}')"
            >
                <div class="email-item-subject">
                    ${emailNumber} — ${escapeHtml(email.subject || "No subject")}
                </div>

                <div class="email-item-sender">
                    ${escapeHtml(email.sender || "Unknown sender")}
                </div>

                <div class="email-item-meta">
                    <span class="email-item-date">
                        ${formatDate(email.created_at)}
                    </span>

                    <span class="email-item-badge">
                        ${escapeHtml(classification)}
                    </span>
                </div>
            </div>
        `;
    }).join("");
}


async function selectEmail(emailId) {
    try {
        const response = await fetch(
            `${API_BASE}/emails/${emailId}`
        );

        if (!response.ok) {
            throw new Error("Failed to load email");
        }

        selectedEmail = await response.json();

        document.querySelectorAll(".email-item").forEach(item => {
            item.classList.remove("active");
        });

        const selectedItem = document.querySelector(
            `.email-item[data-email-id="${emailId}"]`
        );

        if (selectedItem) {
            selectedItem.classList.add("active");
        }

        displayEmail(selectedEmail);

        resetAnalysis();

        // Show saved classification from database
        if (selectedEmail.classification) {
            showClassification(
                selectedEmail.classification,
                selectedEmail.confidence || 0,
                selectedEmail.review_reason,
                selectedEmail.needs_review
            );
        }

        // Fetch saved extraction/comparison data from database
        await loadSavedComparison(emailId);

        addTerminalLog(
            `Selected: ${selectedEmail.subject || "Email"}`,
            "success"
        );

    } catch (error) {
        console.error(error);
        addTerminalLog("Failed to open email", "error");
    }
}


async function loadSavedComparison(emailId) {
    try {
        const response = await fetch(
            `${API_BASE}/emails/${emailId}/comparison`
        );

        if (!response.ok) {
            throw new Error("Failed to load saved comparison");
        }

        const comparison = await response.json();

        // No Comparison row exists yet
        if (!comparison) {
            addTerminalLog(
                "No saved extraction data for this email",
                "warning"
            );

            return;
        }

        /*
         * Comparison row exists.
         * This means extraction has already been performed.
         */

        if (
            comparison.si_fields ||
            comparison.bl_fields
        ) {
            const extractionResults =
                document.getElementById("extraction-results");

            if (extractionResults) {
                extractionResults.classList.remove("hidden");
            }

            displayExtractedFields(
                "si-fields",
                comparison.si_fields
            );

            displayExtractedFields(
                "bl-fields",
                comparison.bl_fields
            );

            document.getElementById(
                "si-result-status"
            ).textContent = "EXTRACTED";

            document.getElementById(
                "bl-result-status"
            ).textContent = "EXTRACTED";

            document.getElementById(
                "extraction-status"
            ).textContent = "COMPLETED";
        }

        /*
         * Only show comparison result if comparison
         * has actually been performed.
         */

        if (
            comparison.mismatches !== null &&
            comparison.result_summary !== null
        ) {
            showComparisonResult(comparison);
        }

        addTerminalLog(
            "Saved analysis loaded from database",
            "success"
        );

    } catch (error) {
        console.error(error);

        addTerminalLog(
            "Failed to load saved analysis",
            "error"
        );
    }
}


function displayEmail(email) {
    const container =
        document.getElementById("email-container");

    container.innerHTML = `
        <div class="email-header">
            <div class="email-subject">
                ${escapeHtml(email.subject || "No subject")}
            </div>

            <div class="email-meta">
                <div class="meta-item">
                    <span class="meta-label">From</span>
                    <span class="meta-value">
                        ${escapeHtml(email.sender || "Unknown")}
                    </span>
                </div>

                <div class="meta-item">
                    <span class="meta-label">Email ID</span>
                    <span class="meta-value">
                        ${escapeHtml(email.id || "—")}
                    </span>
                </div>

                ${email.classification ? `
                    <div class="meta-item">
                        <span class="meta-label">Classification</span>
                        <span class="meta-value">
                            ${escapeHtml(
                                formatCategory(email.classification)
                            )}
                        </span>
                    </div>
                ` : ""}
            </div>
        </div>

        <div class="email-body">
            ${escapeHtml(
                email.body || "No email body available."
            )}
        </div>
    `;
}


async function classifySelectedEmail() {
    if (!selectedEmail) {
        addTerminalLog(
            "Select an email first",
            "warning"
        );
        return;
    }

    const button =
        document.getElementById("classify-btn");

    setButtonLoading(
        button,
        "CLASSIFYING..."
    );

    addTerminalLog(
        "Running AI classification...",
        "warning"
    );

    try {
        const response = await fetch(
            `${API_BASE}/emails/${selectedEmail.id}/classify`,
            {
                method: "POST"
            }
        );

        if (!response.ok) {
            throw new Error("Classification failed");
        }

        const result = await response.json();

        const category =
            result.classification ||
            result.category ||
            result.result ||
            "Unknown";

        const confidence =
            Number(result.confidence ?? 0);

        const reasoning =
            result.review_reason ||
            result.reasoning ||
            result.reason ||
            "";

        selectedEmail.classification = category;
        selectedEmail.confidence = confidence;
        selectedEmail.needs_review =
            result.needs_review ?? confidence < 0.7;
        selectedEmail.review_reason = reasoning;

        showClassification(
            category,
            confidence,
            reasoning,
            selectedEmail.needs_review
        );

        updateEmailBadge(
            selectedEmail.id,
            formatCategory(category)
        );

        addTerminalLog(
            `Classification completed: ${formatCategory(category)}`,
            "success"
        );

    } catch (error) {
        console.error(error);

        addTerminalLog(
            "Classification failed",
            "error"
        );

        setAnalysisError(
            "Classification failed"
        );

    } finally {
        resetButton(
            button,
            "CLASSIFY"
        );
    }
}


function showClassification(
    category,
    confidence,
    reasoning = "",
    needsReview = null
) {
    const formattedCategory =
        formatCategory(category);

    const percentage =
        Math.round(confidence * 100);

    const reviewRequired =
        needsReview !== null
            ? needsReview
            : confidence < 0.7;

    const analysisCategory =
        document.getElementById("analysis-category");

    const analysisResult =
        document.getElementById("analysis-result-category");

    const analysisConfidence =
        document.getElementById("analysis-confidence");

    const analysisConfidenceFill =
        document.getElementById(
            "analysis-confidence-fill"
        );

    const analysisReview =
        document.getElementById(
            "analysis-review-status"
        );

    const analysisReason =
        document.getElementById(
            "analysis-reason"
        );

    const analysisStatus =
        document.getElementById(
            "analysis-status"
        );

    if (analysisCategory) {
        analysisCategory.textContent =
            formattedCategory;
    }

    if (analysisResult) {
        analysisResult.textContent =
            formattedCategory;
    }

    if (analysisConfidence) {
        analysisConfidence.textContent =
            `${percentage}%`;
    }

    if (analysisConfidenceFill) {
        analysisConfidenceFill.style.width =
            `${percentage}%`;
    }

    if (analysisReview) {
        analysisReview.textContent =
            reviewRequired ? "YES" : "NO";

        analysisReview.style.color =
            reviewRequired
                ? "#e9c45d"
                : "#61d8a1";
    }

    if (analysisReason) {
        analysisReason.textContent =
            reasoning ||
            (
                reviewRequired
                    ? "Confidence is below the review threshold."
                    : "Classification completed successfully."
            );
    }

    if (analysisStatus) {
        if (reviewRequired) {
            analysisStatus.textContent =
                "REVIEW";

            analysisStatus.className =
                "analysis-status warning";
        } else {
            analysisStatus.textContent =
                "CLASSIFIED";

            analysisStatus.className =
                "analysis-status success";
        }
    }

    const classificationResult =
        document.getElementById(
            "classification-result"
        );

    const confidenceValue =
        document.getElementById("confidence");

    const confidenceFill =
        document.getElementById(
            "confidence-fill"
        );

    const reason =
        document.getElementById("reason");

    if (classificationResult) {
        classificationResult.textContent =
            formattedCategory;
    }

    if (confidenceValue) {
        confidenceValue.textContent =
            `${percentage}%`;
    }

    if (confidenceFill) {
        confidenceFill.style.width =
            `${percentage}%`;
    }

    if (reason) {
        reason.textContent =
            reasoning ||
            (
                reviewRequired
                    ? "Confidence is below the review threshold."
                    : "Classification completed successfully."
            );
    }
}


async function extractSelectedEmail() {
    if (!selectedEmail) {
        addTerminalLog(
            "Select an email first",
            "warning"
        );
        return;
    }

    const button =
        document.getElementById("extract-btn");

    setButtonLoading(
        button,
        "EXTRACTING..."
    );

    addTerminalLog(
        "Extracting SI and B/L documents...",
        "warning"
    );

    try {
        const response = await fetch(
            `${API_BASE}/extract/${selectedEmail.id}`,
            {
                method: "POST"
            }
        );

        if (!response.ok) {
            const errorData =
                await response.json().catch(() => null);

            throw new Error(
                errorData?.detail ||
                "Extraction failed"
            );
        }

        const result =
            await response.json();

        console.log(
            "Extraction result:",
            result
        );

        const extractionResults =
            document.getElementById(
                "extraction-results"
            );

        if (extractionResults) {
            extractionResults.classList.remove(
                "hidden"
            );
        }

        displayExtractedFields(
            "si-fields",
            result.si_fields
        );

        displayExtractedFields(
            "bl-fields",
            result.bl_fields
        );

        document.getElementById(
            "si-result-status"
        ).textContent = "EXTRACTED";

        document.getElementById(
            "bl-result-status"
        ).textContent = "EXTRACTED";

        document.getElementById(
            "extraction-status"
        ).textContent = "COMPLETED";

        // Extraction creates/updates the database row.
        // Comparison has not been run yet.
        const comparisonResult =
            document.getElementById(
                "comparison-result"
            );

        if (comparisonResult) {
            comparisonResult.classList.add(
                "hidden"
            );
        }

        addTerminalLog(
            "Document extraction completed and saved",
            "success"
        );

    } catch (error) {
        console.error(error);

        addTerminalLog(
            error.message || "Document extraction failed",
            "error"
        );

        const extractionStatus =
            document.getElementById(
                "extraction-status"
            );

        if (extractionStatus) {
            extractionStatus.textContent =
                "FAILED";
        }

    } finally {
        resetButton(
            button,
            "EXTRACT"
        );
    }
}


function displayExtractedFields(
    containerId,
    fields
) {
    const container =
        document.getElementById(containerId);

    if (!container) {
        return;
    }

    if (
        !fields ||
        typeof fields !== "object"
    ) {
        container.innerHTML = `
            <div class="field">
                <span class="field-value">
                    No data extracted
                </span>
            </div>
        `;

        return;
    }

    const excludedFields = [
        "confidence",
        "reasoning",
        "error"
    ];

    const entries =
        Object.entries(fields)
            .filter(([key]) => {
                return !excludedFields.includes(
                    key.toLowerCase()
                );
            });

    if (entries.length === 0) {
        container.innerHTML = `
            <div class="field">
                <span class="field-value">
                    No fields found
                </span>
            </div>
        `;

        return;
    }

    container.innerHTML =
        entries.map(
            ([key, value]) => `
                <div class="field">
                    <span class="field-label">
                        ${escapeHtml(
                            formatFieldName(key)
                        )}
                    </span>

                    <span class="field-value">
                        ${escapeHtml(
                            formatFieldValue(value)
                        )}
                    </span>
                </div>
            `
        ).join("");
}


async function compareSelectedEmail() {
    if (!selectedEmail) {
        addTerminalLog(
            "Select an email first",
            "warning"
        );
        return;
    }

    const button =
        document.getElementById("compare-btn");

    setButtonLoading(
        button,
        "COMPARING..."
    );

    addTerminalLog(
        "Comparing SI and B/L...",
        "warning"
    );

    try {
        const response = await fetch(
            `${API_BASE}/emails/${selectedEmail.id}/compare`,
            {
                method: "POST"
            }
        );

        if (!response.ok) {
            const errorData =
                await response.json().catch(() => null);

            throw new Error(
                errorData?.detail ||
                "Comparison failed"
            );
        }

        const result =
            await response.json();

        console.log(
            "Comparison result:",
            result
        );

        showComparisonResult(result);

        addTerminalLog(
            "SI/B/L comparison completed and saved",
            "success"
        );

    } catch (error) {
        console.error(error);

        addTerminalLog(
            error.message || "Comparison failed",
            "error"
        );

        showComparisonError();

    } finally {
        resetButton(
            button,
            "COMPARE"
        );
    }
}


function showComparisonResult(result) {
    const comparisonBox =
        document.getElementById(
            "comparison-result"
        );

    const status =
        document.getElementById(
            "comparison-status"
        );

    const summary =
        document.getElementById(
            "comparison-summary"
        );

    const mismatchList =
        document.getElementById(
            "mismatch-list"
        );

    if (!comparisonBox) {
        return;
    }

    comparisonBox.classList.remove(
        "hidden"
    );

    const mismatches =
        result.mismatches || [];

    const resultSummary =
        result.result_summary ||
        result.summary ||
        (
            mismatches.length === 0
                ? "No mismatches detected."
                : `${mismatches.length} mismatch(es) detected.`
        );

    const isMatch =
        mismatches.length === 0;

    if (status) {
        status.textContent =
            isMatch
                ? "MATCH"
                : "MISMATCH";

        status.style.color =
            isMatch
                ? "#61d8a1"
                : "#e9c45d";
    }

    if (summary) {
        summary.textContent =
            resultSummary;
    }

    if (mismatchList) {
        if (mismatches.length === 0) {
            mismatchList.innerHTML = `
                <div class="mismatch-item">
                    <div class="mismatch-field">
                        ✓ No mismatches detected
                    </div>

                    <div class="mismatch-values">
                        SI and B/L information is consistent.
                    </div>
                </div>
            `;
        } else {
            mismatchList.innerHTML =
                mismatches
                    .map(mismatch =>
                        renderMismatch(mismatch)
                    )
                    .join("");
        }
    }
}


function renderMismatch(mismatch) {
    if (typeof mismatch === "string") {
        return `
            <div class="mismatch-item">
                <div class="mismatch-field">
                    ${escapeHtml(mismatch)}
                </div>
            </div>
        `;
    }

    const field =
        mismatch.field ||
        mismatch.key ||
        mismatch.name ||
        "Field";

    const siValue =
        mismatch.si_value ??
        mismatch.si ??
        mismatch.siValue ??
        "—";

    const blValue =
        mismatch.bl_value ??
        mismatch.bl ??
        mismatch.blValue ??
        "—";

    return `
        <div class="mismatch-item">
            <div class="mismatch-field">
                ${escapeHtml(
                    formatFieldName(field)
                )}
            </div>

            <div class="mismatch-values">
                SI: ${escapeHtml(
                    formatFieldValue(siValue)
                )}
                <br>
                B/L: ${escapeHtml(
                    formatFieldValue(blValue)
                )}
            </div>
        </div>
    `;
}


function showComparisonError() {
    const comparisonBox =
        document.getElementById(
            "comparison-result"
        );

    const status =
        document.getElementById(
            "comparison-status"
        );

    const summary =
        document.getElementById(
            "comparison-summary"
        );

    const mismatchList =
        document.getElementById(
            "mismatch-list"
        );

    if (comparisonBox) {
        comparisonBox.classList.remove(
            "hidden"
        );
    }

    if (status) {
        status.textContent =
            "ERROR";

        status.style.color =
            "#ed7481";
    }

    if (summary) {
        summary.textContent =
            "Unable to complete document comparison.";
    }

    if (mismatchList) {
        mismatchList.innerHTML = "";
    }
}


function resetAnalysis() {
    const analysisConfidence =
        document.getElementById(
            "analysis-confidence"
        );

    const analysisConfidenceFill =
        document.getElementById(
            "analysis-confidence-fill"
        );

    const analysisCategory =
        document.getElementById(
            "analysis-category"
        );

    const analysisResult =
        document.getElementById(
            "analysis-result-category"
        );

    const analysisReview =
        document.getElementById(
            "analysis-review-status"
        );

    const analysisReason =
        document.getElementById(
            "analysis-reason"
        );

    const analysisStatus =
        document.getElementById(
            "analysis-status"
        );

    const confidence =
        document.getElementById(
            "confidence"
        );

    const confidenceFill =
        document.getElementById(
            "confidence-fill"
        );

    const classificationResult =
        document.getElementById(
            "classification-result"
        );

    const reason =
        document.getElementById(
            "reason"
        );

    const extractionResults =
        document.getElementById(
            "extraction-results"
        );

    const comparisonResult =
        document.getElementById(
            "comparison-result"
        );

    if (analysisConfidence) {
        analysisConfidence.textContent =
            "—";
    }

    if (analysisConfidenceFill) {
        analysisConfidenceFill.style.width =
            "0%";
    }

    if (analysisCategory) {
        analysisCategory.textContent =
            "Waiting for classification";
    }

    if (analysisResult) {
        analysisResult.textContent =
            "Waiting";
    }

    if (analysisReview) {
        analysisReview.textContent =
            "—";

        analysisReview.style.color =
            "";
    }

    if (analysisReason) {
        analysisReason.textContent =
            "Classification has not been performed yet.";
    }

    if (analysisStatus) {
        analysisStatus.textContent =
            "WAITING";

        analysisStatus.className =
            "analysis-status neutral";
    }

    if (confidence) {
        confidence.textContent =
            "—";
    }

    if (confidenceFill) {
        confidenceFill.style.width =
            "0%";
    }

    if (classificationResult) {
        classificationResult.textContent =
            "Waiting";
    }

    if (reason) {
        reason.textContent =
            "No classification performed yet.";
    }

    if (extractionResults) {
        extractionResults.classList.add(
            "hidden"
        );
    }

    if (comparisonResult) {
        comparisonResult.classList.add(
            "hidden"
        );
    }

    const siFields =
        document.getElementById(
            "si-fields"
        );

    const blFields =
        document.getElementById(
            "bl-fields"
        );

    const siStatus =
        document.getElementById(
            "si-result-status"
        );

    const blStatus =
        document.getElementById(
            "bl-result-status"
        );

    const extractionStatus =
        document.getElementById(
            "extraction-status"
        );

    if (siFields) {
        siFields.innerHTML =
            "No data extracted";
    }

    if (blFields) {
        blFields.innerHTML =
            "No data extracted";
    }

    if (siStatus) {
        siStatus.textContent =
            "WAITING";
    }

    if (blStatus) {
        blStatus.textContent =
            "WAITING";
    }

    if (extractionStatus) {
        extractionStatus.textContent =
            "WAITING";
    }
}


function setAnalysisError(message) {
    const status =
        document.getElementById(
            "analysis-status"
        );

    const reason =
        document.getElementById(
            "analysis-reason"
        );

    if (status) {
        status.textContent =
            "ERROR";

        status.className =
            "analysis-status error";
    }

    if (reason) {
        reason.textContent =
            message;
    }
}


function setupCategories() {
    document.querySelectorAll(
        ".category"
    ).forEach(category => {

        category.addEventListener(
            "click",
            () => {

                document.querySelectorAll(
                    ".category"
                ).forEach(item => {
                    item.classList.remove(
                        "active"
                    );
                });

                category.classList.add(
                    "active"
                );

                const filter =
                    category.dataset.category;

                filterEmails(filter);
            }
        );
    });
}


function filterEmails(filter) {
    let filtered = emails;

    if (filter === "pending") {
        filtered =
            emails.filter(email =>
                !email.classification
            );
    }

    if (filter === "review") {
        filtered =
            emails.filter(email =>
                email.needs_review === true
            );
    }

    if (filter === "completed") {
        filtered =
            emails.filter(email =>
                !!email.classification
            );
    }

    renderEmailList(filtered);
}


function updateEmailBadge(
    emailId,
    text
) {
    const emailItem =
        document.querySelector(
            `.email-item[data-email-id="${emailId}"]`
        );

    if (!emailItem) {
        return;
    }

    const badge =
        emailItem.querySelector(
            ".email-item-badge"
        );

    if (badge) {
        badge.textContent =
            text;
    }
}


function addTerminalLog(
    message,
    type = ""
) {
    const terminal =
        document.getElementById(
            "terminal"
        );

    if (!terminal) {
        return;
    }

    const time =
        new Date().toLocaleTimeString(
            [],
            {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }
        );

    const line =
        document.createElement(
            "div"
        );

    line.className =
        `terminal-line ${type}`;

    line.textContent =
        `[${time}] ${message}`;

    terminal.appendChild(line);

    terminal.scrollTop =
        terminal.scrollHeight;
}


function setButtonLoading(
    button,
    text
) {
    if (!button) {
        return;
    }

    button.disabled = true;

    button.dataset.originalText =
        button.textContent;

    button.textContent =
        text;
}


function resetButton(
    button,
    text
) {
    if (!button) {
        return;
    }

    button.disabled = false;
    button.textContent = text;
}


function formatCategory(category) {
    if (!category) {
        return "Unknown";
    }

    return String(category)
        .replace(/[_-]/g, " ")
        .replace(
            /\b\w/g,
            char => char.toUpperCase()
        );
}


function formatFieldName(key) {
    return String(key)
        .replace(/_/g, " ")
        .replace(/-/g, " ")
        .replace(
            /\b\w/g,
            char => char.toUpperCase()
        );
}


function formatFieldValue(value) {
    if (
        value === null ||
        value === undefined
    ) {
        return "—";
    }

    if (typeof value === "object") {
        return JSON.stringify(value);
    }

    return String(value);
}


function formatDate(date) {
    if (!date) {
        return "—";
    }

    const parsedDate =
        new Date(date);

    if (
        Number.isNaN(
            parsedDate.getTime()
        )
    ) {
        return "—";
    }

    return parsedDate.toLocaleDateString();
}


function escapeHtml(value) {
    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    return String(value)
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );
}