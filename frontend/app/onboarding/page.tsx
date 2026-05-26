import React, { useState } from "react";
import { useRouter } from "next/router";
import { cn } from "@/lib/utils";
import { Button, Input, Textarea } from "@/components/ui";

const OnboardingWizard = () => {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    name: "",
    imapHost: "",
    imapPort: 993,
    imapUsername: "",
    imapPassword: "",
    smtpHost: "",
    smtpPort: 587,
    smtpUsername: "",
    smtpPassword: "",
  });

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async () => {
    try {
      switch (step) {
        case 1:
          // Validate and test IMAP connection
          if (
            !formData.imapHost ||
            !formData.imapUsername ||
            !formData.imapPasswordEnc ||
            !formData.smtpHost ||
            !formData.smtpUsername ||
            !formData.smtpPasswordEnc
          ) {
            alert("Please fill in all fields.");
            return;
          }

          const isImapConnected = await pollImap(
            formData.imapHost,
            formData.imapPort,
            formData.imapUsername,
            formData.imapPasswordEnc
          );

          if (!isImapConnected) {
            alert("Failed to connect to IMAP. Please check your credentials.");
            return;
          }

          // Proceed to the next step
          setStep(2);
          break;

        case 2:
          // Create organisation and save form data
          const response = await fetch("/api/v1/onboarding/setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(formData),
          });

          if (response.ok) {
            const orgData = await response.json();
            alert("Organisation created successfully!");
            router.push(`/onboarding/status?id=${orgData.id}`);
          } else {
            alert("Failed to create organisation. Please try again.");
          }
          break;

        default:
          // Handle unexpected step
          console.error(`Invalid step: ${step}`);
      }
    } catch (error) {
      console.error("Error during onboarding:", error);
      alert("An error occurred during the onboarding process. Please try again later.");
    }
  };

  const pollImap = async (
    host: string,
    port: number,
    username: string,
    passwordEnc: string
  ) => {
    // Decrypt password
    const password = decrypt(passwordEnc);

    // Connect to IMAP server
    const imap = new imap({
      user: username,
      password: password,
      host: host,
      port: port,
      secure: true,
    });

    try {
      await imap.connect();
      await imap.select("INBOX");

      // Search for unread messages
      const status = await imap.search(["UNSEEN"]);
      if (status.length === 0) {
        return false;
      }

      return true;
    } catch (error) {
      console.error("Error polling IMAP:", error);
      return false;
    } finally {
      await imap.end();
    }
  };

  const handleTestImap = async () => {
    try {
      if (
        !formData.imapHost ||
        !formData.imapUsername ||
        !formData.smtpHost ||
        !formData.smtpUsername
      ) {
        alert("Please fill in all fields.");
        return;
      }

      const isImapConnected = await pollImap(
        formData.imapHost,
        formData.imapPort,
        formData.imapUsername,
        formData.imapPasswordEnc
      );

      if (isImapConnected) {
        alert("IMAP connection successful!");
      } else {
        alert("Failed to connect to IMAP. Please check your credentials.");
      }
    } catch (error) {
      console.error("Error testing IMAP:", error);
      alert("An error occurred during the IMAP test. Please try again later.");
    }
  };

  return (
    <div className="flex flex-col items-center justify-center h-screen">
      {step === 1 && (
        <form onSubmit={handleSubmit} className="w-full max-w-md p-4 bg-white rounded shadow-md">
          <h2 className="text-2xl font-bold mb-4">Organisation Setup</h2>
          <div className="mb-4">
            <label htmlFor="name" className="block text-gray-700 font-bold mb-2">
              Organisation Name
            </label>
            <Input
              id="name"
              name="name"
              type="text"
              value={formData.name}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="mb-4">
            <label htmlFor="imapHost" className="block text-gray-700 font-bold mb-2">
              IMAP Host
            </label>
            <Input
              id="imapHost"
              name="imapHost"
              type="text"
              value={formData.imapHost}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="mb-4">
            <label htmlFor="imapPort" className="block text-gray-700 font-bold mb-2">
              IMAP Port
            </label>
            <Input
              id="imapPort"
              name="imapPort"
              type="number"
              value={formData.imapPort}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="mb-4">
            <label htmlFor="imapUsername" className="block text-gray-700 font-bold mb-2">
              IMAP Username
            </label>
            <Input
              id="imapUsername"
              name="imapUsername"
              type="text"
              value={formData.imapUsername}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="mb-4">
            <label htmlFor="imapPasswordEnc" className="block text-gray-700 font-bold mb-2">
              IMAP Password (Encrypted)
            </label>
            <Input
              id="imapPasswordEnc"
              name="imapPasswordEnc"
              type="text"
              value={formData.imapPasswordEnc}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="mb-4">
            <label htmlFor="smtpHost" className="block text-gray-700 font-bold mb-2">
              SMTP Host
            </label>
            <Input
              id="smtpHost"
              name="smtpHost"
              type="text"
              value={formData.smtpHost}
              onChange={handleInputChange}
              required
            />
          </div>
          <div className="mb-4">
            <label htmlFor="smtpPort" className