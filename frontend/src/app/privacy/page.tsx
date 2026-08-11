import type { Metadata } from "next"
import Link from "next/link"
import LegalPageShell, { LegalSection } from "@/components/legal/LegalPageShell"

export const metadata: Metadata = {
  title: "Privacy Policy — Movie Clips",
  description: "Privacy Policy for Movie Clips by Purple Merit",
  robots: { index: true, follow: true },
}

const EFFECTIVE_DATE = "August 11, 2026"
const CONTACT_EMAIL = "privacy@purplemerit.shop"

export default function PrivacyPolicyPage() {
  return (
    <LegalPageShell title="Privacy Policy" effectiveDate={EFFECTIVE_DATE}>
      <LegalSection title="1. Who we are">
        <p>
          This Privacy Policy describes how <strong>Purple Merit</strong> (“we”, “us”, or “our”) collects, uses, and
          shares information when you use <strong>Movie Clips</strong> (also referred to as Clip AI), available at{" "}
          <a href="https://vid-editor-tan.vercel.app">https://vid-editor-tan.vercel.app</a> (the “Service”).
        </p>
        <p>
          Privacy questions or requests:{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        </p>
      </LegalSection>

      <LegalSection title="2. Information we collect">
        <p>Depending on how you use the Service, we may collect:</p>
        <ul>
          <li>
            <strong>Account data:</strong> email address, name, and a hashed password when you register.
          </li>
          <li>
            <strong>Content you provide:</strong> videos you upload, YouTube URLs you submit, projects, clips, captions,
            and related metadata (for example titles, timestamps, and file sizes).
          </li>
          <li>
            <strong>Connected account data:</strong> if you connect YouTube or Instagram/Facebook, we receive OAuth
            tokens and account identifiers needed to publish content on your behalf. We do not receive your social
            login password.
          </li>
          <li>
            <strong>Usage and technical data:</strong> IP address, browser type, device information, and basic logs
            needed to operate, secure, and debug the Service.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="3. How we use information">
        <p>We use information to:</p>
        <ul>
          <li>Create and manage your account</li>
          <li>Process videos into short clips and generate AI summaries/captions</li>
          <li>Store and deliver media (including via cloud storage and file hosts you choose to use)</li>
          <li>Publish clips to platforms you connect (such as YouTube Shorts or Instagram Reels)</li>
          <li>Provide support, improve the Service, and protect against abuse or fraud</li>
          <li>Comply with legal obligations</li>
        </ul>
      </LegalSection>

      <LegalSection title="4. AI processing">
        <p>
          To generate transcripts, summaries, and captions, we may send portions of your audio/video content or derived
          text to third-party AI providers such as <strong>OpenAI</strong> and/or <strong>Google Gemini</strong>. Those
          providers process data under their own terms and privacy policies.
        </p>
      </LegalSection>

      <LegalSection title="5. Third-party services">
        <p>We rely on service providers to operate Movie Clips, which may include:</p>
        <ul>
          <li>
            <strong>Cloudinary</strong> and/or our hosting/FTP storage for media files
          </li>
          <li>
            <strong>Optional file hosts</strong> (for example KrakenFiles, Uploadrar, Up-4ever) when you distribute clips
          </li>
          <li>
            <strong>YouTube / Google</strong> and <strong>Instagram / Meta (Facebook)</strong> for OAuth and publishing
          </li>
          <li>
            <strong>OpenAI</strong> and <strong>Google Gemini</strong> for AI features
          </li>
          <li>Hosting, database, and infrastructure providers (for example Vercel, MongoDB, Redis)</li>
        </ul>
        <p>
          When you publish to YouTube or Instagram, content and captions are shared with those platforms according to
          your settings and their policies.
        </p>
      </LegalSection>

      <LegalSection title="6. Meta / Instagram and Google / YouTube data">
        <p>
          If you connect Instagram (via Meta) or YouTube (via Google), we use the permissions you grant only to
          authenticate your account and publish content you choose to post. We do not sell this data. You can disconnect
          access in the Service and/or revoke access in your Meta or Google account settings.
        </p>
      </LegalSection>

      <LegalSection title="7. Cookies and similar technologies">
        <p>
          We use essential storage (such as authentication tokens in your browser) to keep you signed in and operate the
          Service. We do not use advertising cookies.
        </p>
      </LegalSection>

      <LegalSection title="8. Data retention">
        <p>
          We retain account and project data while your account is active and for a reasonable period afterward as
          needed for backups, legal compliance, dispute resolution, and security. Media files may be removed when you
          delete projects or when storage policies require cleanup.
        </p>
      </LegalSection>

      <LegalSection title="9. Security">
        <p>
          We use reasonable technical and organizational measures to protect information, including hashed passwords and
          access controls. No method of transmission or storage is 100% secure.
        </p>
      </LegalSection>

      <LegalSection title="10. Your rights">
        <p>
          Depending on where you live, you may have rights to access, correct, delete, or export your personal data, or
          to object to certain processing. To exercise these rights, contact us at{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
      </LegalSection>

      <LegalSection id="data-deletion" title="11. User data deletion">
        <p>
          You may request deletion of your Movie Clips account and associated personal data by emailing{" "}
          <a href={`mailto:${CONTACT_EMAIL}?subject=Data%20Deletion%20Request`}>{CONTACT_EMAIL}</a> from the email
          address on your account, with the subject line <strong>“Data Deletion Request”</strong>.
        </p>
        <p>Please include:</p>
        <ul>
          <li>The email address registered to your account</li>
          <li>A clear request to delete your account and personal data</li>
        </ul>
        <p>
          We will verify the request and delete or anonymize personal data associated with your account within a
          reasonable period (typically within 30 days), except where we must retain information for legal, security, or
          operational reasons (for example fraud prevention or dispute records).
        </p>
        <p>
          Content already published to YouTube, Instagram, or third-party file hosts may remain on those platforms; you
          should remove it there if you want it deleted from those services.
        </p>
        <p>
          You can also revoke platform permissions at any time via your{" "}
          <a href="https://www.facebook.com/settings?tab=applications" target="_blank" rel="noreferrer">
            Meta Apps and Websites settings
          </a>{" "}
          or{" "}
          <a href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer">
            Google Account permissions
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection title="12. Children’s privacy">
        <p>
          The Service is not directed to children under 13 (or the minimum age required in your jurisdiction). We do not
          knowingly collect personal information from children.
        </p>
      </LegalSection>

      <LegalSection title="13. International transfers">
        <p>
          Your information may be processed in countries other than where you live. Where required, we take steps to
          protect transferred data in accordance with applicable law.
        </p>
      </LegalSection>

      <LegalSection title="14. Changes to this policy">
        <p>
          We may update this Privacy Policy from time to time. We will post the updated version on this page and revise
          the effective date above. Continued use of the Service after changes means you accept the updated policy.
        </p>
      </LegalSection>

      <LegalSection title="15. Contact">
        <p>
          Purple Merit — Movie Clips
          <br />
          Email: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
          <br />
          Related: <Link href="/terms">Terms of Service</Link>
        </p>
      </LegalSection>
    </LegalPageShell>
  )
}
